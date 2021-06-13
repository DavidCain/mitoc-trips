"""
Allows maintenance of Google Spreadsheets with membership information.

Users can opt-in to have their information shared with third parties.

These methods will post information about users' membership status to Google
spreadsheets. Each spreadsheet will be shared with the company offering the
discount, so that they can verify membership status.
"""
import bisect
import functools
import logging
import os.path
import typing
from itertools import zip_longest

import gspread
import httplib2
from oauth2client.service_account import ServiceAccountCredentials

from ws import enums, models, settings
from ws.utils import geardb
from ws.utils.perms import is_chair

logger = logging.getLogger(__name__)


# Initialize just one client, which can be re-used & refreshed
@functools.lru_cache(maxsize=None)
def connect_to_sheets():
    """Returns a Google Sheets client and the creds used by that client.

    If intentionally disabling Google Sheets functionality, `None` will be
    returned as both the client and client credentials. This occurs even if the
    proper credential file is present.

    If missing credentials while in DEBUG mode, a "soft failure" will occur:
    the logger will note the missing credentials file and will return `None`
    for both client and credentials.

    This allows us to run a webserver in a development environment that will
    never actually update Google spreadsheets. We can go through the flow of
    modifying discounts without running a Celery job to update the spreadsheet.
    """
    scope = ['https://spreadsheets.google.com/feeds']
    credfile = settings.OAUTH_JSON_CREDENTIALS
    creds_present = credfile and os.path.exists(credfile)

    # Avoid unnecessary handshake with a service we'll never use
    if settings.DISABLE_GSHEETS:
        return None, None

    if not creds_present:
        if settings.DEBUG:
            logger.error(
                "OAUTH_JSON_CREDENTIALS is missing! " "Unable to update Google Sheets."
            )
            return None, None
        raise KeyError("Specify OAUTH_JSON_CREDENTIALS to update Google Sheets")

    credentials = ServiceAccountCredentials.from_json_keyfile_name(credfile, scope)
    return gspread.authorize(credentials), credentials


def with_refreshed_token(func):
    """By default, tokens are limited to 60 minutes. Refresh if expired."""

    def func_wrapper(*args, **kwargs):
        client, credentials = connect_to_sheets()
        if credentials.access_token_expired:
            credentials.refresh(httplib2.Http())  # (`client` points to this)
            client.login()  # Log in again to refresh credentials
        func(*args, **kwargs)

    return func_wrapper


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


class SpreadsheetLabels(typing.NamedTuple):
    name: str
    email: str
    membership: str
    access: str
    leader: str
    student: str
    school: str


class SheetWriter:
    """Utility methods for formatting a row in discount worksheets."""

    # Use constants to refer to columns
    labels = SpreadsheetLabels(
        name='Name',
        email='Email',
        membership='Membership Status',
        access='Access Level',
        leader='Leader Status',
        student='Student Status',
        school='School',
    )

    def __init__(self, discount):
        """Identify the columns that will be used in the spreadsheet."""
        self.discount = discount

        # These columns appear in all discount sheets
        self.header = [self.labels.name, self.labels.email, self.labels.membership]

        # Depending on properties of the discount, include additional cols
        extra_optional_columns = [
            (self.labels.access, discount.report_access),
            (self.labels.leader, discount.report_leader),
            (self.labels.student, discount.report_student),
            (self.labels.school, discount.report_school),
        ]
        for label, should_include in extra_optional_columns:
            if should_include:
                self.header.append(label)

    @staticmethod
    def activity_descriptors(participant, user):
        """Yield a description for each activity the participant is a leader.

        Mentions if the person is a leader or a chair, but does not give their
        specific ranking.
        """
        active_ratings = participant.leaderrating_set.filter(active=True)
        for activity in active_ratings.values_list('activity', flat=True):
            activity_enum = enums.Activity(activity)
            position = 'chair' if is_chair(user, activity_enum, False) else 'leader'
            yield f"{activity_enum.label} {position}"

    def leader_text(self, participant, user):
        return ', '.join(self.activity_descriptors(participant, user))

    @staticmethod
    def school(participant):
        """Return what school participant goes to, if applicable."""
        if not participant.is_student:
            return 'N/A'
        if participant.affiliation in {'MU', 'MG'}:
            return 'MIT'
        return 'Other'  # We don't collect non-MIT affiliation

    def access_text(self, participant):
        """Simple string indicating level of access person should have."""
        if self.discount.administrators.filter(pk=participant.pk).exists():
            return 'Admin'
        if participant.is_leader:
            return 'Leader'
        if participant.is_student:
            return 'Student'
        return 'Standard'

    @staticmethod
    def membership_status(user):
        """Return membership status, irrespective of waiver status.

        (Companies don't care about participant waiver status, so ignore it).
        """
        # Status is one external query per user. Expensive! (We should refactor...)
        membership = geardb.user_membership_expiration(user)['membership']

        # We report Active/Expired, since companies don't care about waiver status
        if membership['active']:
            return 'Active'
        if membership['expires']:
            return 'Expired {}'.format(membership['expires'].isoformat())
        return 'Missing'

    def get_row(self, participant, user):
        """Get the row values that match the header for this discount sheet."""
        row_mapper = {
            self.labels.name: participant.name,
            self.labels.email: participant.email,
            self.labels.membership: self.membership_status(user),
            self.labels.student: participant.get_affiliation_display(),
            self.labels.school: self.school(participant),
        }

        # Only fetch these if needed, as we hit the database
        if self.labels.leader in self.header:
            row_mapper[self.labels.leader] = self.leader_text(participant, user)
        if self.labels.access in self.header:
            row_mapper[self.labels.access] = self.access_text(participant)

        return [row_mapper[label] for label in self.header]


def assign(cells, values):
    for cell, value in zip(cells, values):
        cell.value = value


@with_refreshed_token
def update_participant(discount, participant):
    """Add or update the participant.

    Much more efficient than updating the entire sheet.
    """
    user = models.User.objects.get(pk=participant.user_id)
    client, _ = connect_to_sheets()
    wks = client.open_by_key(discount.ga_key).sheet1
    writer = SheetWriter(discount)

    new_row = writer.get_row(participant, user)

    # Attempt to find existing row, update it if found
    last_col = len(writer.header)
    for cell in wks.findall(participant.email):
        if cell.col == 2:  # (Participants _could_ name themselves an email...)
            # pylint: disable=too-many-function-args
            row_cells = wks.range(cell.row, cell.col, cell.row, last_col)
            assign(row_cells, new_row)
            return

    # Insert a new row if no existing row found
    sorted_names = wks.col_values(1)[1:]
    row_index = bisect.bisect(sorted_names, participant.name) + 1
    wks.insert_row(new_row, row_index + 1)


@with_refreshed_token
def update_discount_sheet(discount):
    """Update the entire worksheet, updating all members' status.

    This will remove members who no longer wish to share their information,
    so it's important to run this periodically.

    For individual updates, this approach should be avoided (instead, opting to
    update individual cells in the spreadsheet).
    """
    client, _ = connect_to_sheets()
    wks = client.open_by_key(discount.ga_key).sheet1
    participants = list(discount.participant_set.order_by('name'))

    users = models.User.objects.filter(pk__in=[p.user_id for p in participants])
    user_by_id = {user.pk: user for user in users}

    writer = SheetWriter(discount)

    # Resize sheet to exact size, select all cells
    num_rows, num_cols = len(participants) + 1, len(writer.header)
    wks.resize(num_rows, num_cols)
    # pylint: disable=too-many-function-args
    all_cells = wks.range(1, 1, num_rows, num_cols)
    rows = grouper(all_cells, len(writer.header))

    assign(next(rows), writer.header)

    # Update each row with current membership information
    for participant, row in zip(participants, rows):
        user = user_by_id[participant.user_id]
        assign(row, writer.get_row(participant, user))

    # Batch update to minimize API calls
    wks.update_cells(all_cells)
