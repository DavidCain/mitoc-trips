"""
Allows maintenance of Google Spreadsheets with membership information.

Users can opt-in to have their information shared with third parties.

These methods will post information about users' membership status to Google
spreadsheets. Each spreadsheet will be shared with the company offering the
discount, so that they can verify membership status.
"""
import bisect
import logging
import os.path
from itertools import zip_longest
from typing import Iterator, NamedTuple, Tuple

import gspread
import requests
from google.oauth2.service_account import Credentials
from mitoc_const import affiliations

from ws import enums, models, settings
from ws.utils import membership as membership_utils
from ws.utils.perms import is_chair

logger = logging.getLogger(__name__)

MIT_STUDENT_AFFILIATIONS = frozenset(
    [
        affiliations.MIT_GRAD_STUDENT.CODE,
        affiliations.MIT_UNDERGRAD.CODE,
    ]
)


def connect_to_sheets() -> gspread.client.Client:
    """Returns a Google Sheets client

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
    scopes = ['https://spreadsheets.google.com/feeds']
    credfile = settings.OAUTH_JSON_CREDENTIALS
    creds_present = credfile and os.path.exists(credfile)

    # Avoid unnecessary handshake with a service we'll never use
    if settings.DISABLE_GSHEETS:
        return None, None

    if not creds_present:
        if settings.DEBUG:
            logger.error(
                "OAUTH_JSON_CREDENTIALS is missing! Unable to update Google Sheets."
            )
            return None, None
        raise KeyError("Specify OAUTH_JSON_CREDENTIALS to update Google Sheets")

    credentials = Credentials.from_service_account_file(credfile, scopes=scopes)
    return gspread.authorize(credentials)


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


class SpreadsheetLabels(NamedTuple):
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

    discount: models.Discount
    header: Tuple[str, ...]

    def __init__(self, discount: models.Discount):
        """Identify the columns that will be used in the spreadsheet."""
        self.discount = discount
        self.header = self._header_for_discount(discount)

    def _header_for_discount(self, discount: models.Discount) -> Tuple[str, ...]:
        # These columns appear in all discount sheets
        header = [self.labels.name, self.labels.email, self.labels.membership]

        # Depending on properties of the discount, include additional cols
        extra_optional_columns = [
            (self.labels.access, discount.report_access),
            (self.labels.leader, discount.report_leader),
            (self.labels.student, discount.report_student),
            (self.labels.school, discount.report_school),
        ]
        for label, should_include in extra_optional_columns:
            if should_include:
                header.append(label)

        return tuple(header)

    @staticmethod
    def activity_descriptors(participant: models.Participant) -> Iterator[str]:
        """Yield a description for each activity the participant is a leader.

        Mentions if the person is a leader or a chair, but does not give their
        specific ranking.
        """
        active_ratings = participant.leaderrating_set.filter(active=True)
        for activity in active_ratings.values_list('activity', flat=True):
            activity_enum = enums.Activity(activity)
            position = (
                'chair'
                if is_chair(participant.user, activity_enum, False)
                else 'leader'
            )
            yield f"{activity_enum.label} {position}"

    def leader_text(self, participant: models.Participant) -> str:
        return ', '.join(self.activity_descriptors(participant))

    @staticmethod
    def school(participant: models.Participant) -> str:
        """Return what school participant goes to, if applicable."""
        if not participant.is_student:
            return 'N/A'
        if participant.affiliation in MIT_STUDENT_AFFILIATIONS:
            return 'MIT'
        return 'Other'  # We don't collect non-MIT affiliation

    def access_text(self, participant: models.Participant) -> str:
        """Simple string indicating level of access person should have."""
        if self.discount.administrators.filter(pk=participant.pk).exists():
            return 'Admin'
        if participant.is_leader:
            return 'Leader'
        if participant.is_student:
            return 'Student'
        return 'Standard'

    @staticmethod
    def membership_status(participant: models.Participant) -> str:
        """Return membership status, irrespective of waiver status.

        (Companies don't care about participant waiver status, so ignore it).
        """
        # For most participants, the cache will have an active membership!
        if participant and participant.membership_active:
            return 'Active'

        # Status is one API query per user. Expensive! (We should refactor...)
        try:
            membership = membership_utils.get_latest_membership(participant)
        except requests.exceptions.RequestException:
            logger.exception("Error fetching membership information!")
            # This is hopefully a temporary error...
            # Discount sheets are re-generated every day at the very least.
            # Avoid breaking the whole sheet for all users; continue on
            return 'Unknown'

        # We report Active/Expired, since companies don't care about waiver status
        if membership.membership_active:
            return 'Active'
        if membership.membership_expires:
            return f'Expired {membership.membership_expires.isoformat()}'
        return 'Missing'

    def get_row(self, participant: models.Participant) -> Tuple[str, ...]:
        """Get the row values that match the header for this discount sheet."""
        row_mapper = {
            self.labels.name: participant.name,
            self.labels.email: participant.email,
            self.labels.membership: self.membership_status(participant),
            self.labels.student: participant.get_affiliation_display(),
            self.labels.school: self.school(participant),
        }

        # Only fetch these if needed, as we hit the database
        if self.labels.leader in self.header:
            row_mapper[self.labels.leader] = self.leader_text(participant)
        if self.labels.access in self.header:
            row_mapper[self.labels.access] = self.access_text(participant)

        return tuple(row_mapper[label] for label in self.header)


def _assign(cells, values):
    for cell, value in zip(cells, values):
        cell.value = value


def update_participant(
    discount: models.Discount,
    participant: models.Participant,
) -> None:
    """Add or update the participant.

    Much more efficient than updating the entire sheet.
    """
    client = connect_to_sheets()
    wks = client.open_by_key(discount.ga_key).sheet1
    writer = SheetWriter(discount)

    new_row = writer.get_row(participant)

    # Attempt to find existing row, update it if found
    last_col = len(writer.header)
    for cell in wks.findall(participant.email):
        if cell.col == 2:  # (Participants _could_ name themselves an email...)
            # pylint: disable=too-many-function-args
            row_cells = wks.range(cell.row, cell.col, cell.row, last_col)
            _assign(row_cells, new_row)
            return

    # Insert a new row if no existing row found
    sorted_names = wks.col_values(1)[1:]
    row_index = bisect.bisect(sorted_names, participant.name) + 1
    wks.insert_row(new_row, row_index + 1)


def update_discount_sheet(discount: models.Discount) -> None:
    """Update the entire worksheet, updating all members' status.

    This will remove members who no longer wish to share their information,
    so it's important to run this periodically.

    For individual updates, this approach should be avoided (instead, opting to
    update individual cells in the spreadsheet).
    """
    client = connect_to_sheets()
    wks = client.open_by_key(discount.ga_key).sheet1
    participants = list(
        discount.participant_set.select_related('membership', 'user').order_by('name')
    )

    writer = SheetWriter(discount)

    # Resize sheet to exact size, select all cells
    num_rows, num_cols = len(participants) + 1, len(writer.header)
    wks.resize(num_rows, num_cols)
    # pylint: disable=too-many-function-args
    all_cells = wks.range(1, 1, num_rows, num_cols)
    rows = grouper(all_cells, len(writer.header))

    _assign(next(rows), writer.header)

    # Update each row with current membership information
    for participant, row in zip(participants, rows):
        _assign(row, writer.get_row(participant))

    # Batch update to minimize API calls
    wks.update_cells(all_cells)
