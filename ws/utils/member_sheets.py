"""
Allows maintenance of Google Spreadsheets with membership information.

Users can opt-in to have their information shared with third parties.

These methods will post information about users' membership status to Google
spreadsheets. Each spreadsheet will be shared with the company offering the
discount, so that they can verify membership status.
"""
import bisect
from collections import OrderedDict, namedtuple
from itertools import zip_longest
import httplib2
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from ws import models
from ws import settings
from ws.utils import geardb
from ws.utils.perms import activity_name, is_chair


scope = ['https://spreadsheets.google.com/feeds']
credfile = os.getenv('OAUTH_JSON_CREDENTIALS')
if settings.DEBUG and not credfile:  # Allow local environments to skip
    credentials = None  # Exceptions will be raised if any methods are tried
    gc = None
else:
    credentials = ServiceAccountCredentials.from_json_keyfile_name(credfile, scope)
    gc = gspread.authorize(credentials)


def with_refreshed_token(func):
    """ By default, tokens are limited to 60 minutes. Refresh if expired. """
    def func_wrapper(*args, **kwargs):
        if credentials.access_token_expired:
            credentials.refresh(httplib2.Http())
            gc.login()  # Client stored credentials, so log in again to refresh
        func(*args, **kwargs)
    return func_wrapper


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


class SheetWriter(object):
    """ Utility methods for formatting a row in discount worksheets. """

    # Use constants to refer to columns
    col_constants = OrderedDict(
        name='Name',
        email='Email',
        membership='Membership Status',
        access='Access Level',
        leader='Leader Status',
        student='Student Status',
        school='School'
    )
    labels = namedtuple('SpreadsheetLabels', col_constants)(**col_constants)

    def __init__(self, discount):
        """ Identify the columns that will be used in the spreadsheet. """
        self.discount = discount

        # These columns appear in all discount sheets
        self.header = [
            self.labels.name,
            self.labels.email,
            self.labels.membership
        ]

        # Depending on properties of the discount, include additional cols
        extra_optional_columns = [
            (self.labels.access, discount.report_access),
            (self.labels.leader, discount.report_leader),
            (self.labels.student, discount.report_student),
            (self.labels.school, discount.report_school)
        ]
        for label, should_include in extra_optional_columns:
            if should_include:
                self.header.append(label)

    @staticmethod
    def activity_descriptors(participant, user):
        """ Yield a description for each activity the participant is a leader.

        Mentions if the person is a leader or a chair, but does not give their
        specific ranking.
        """
        active_ratings = participant.leaderrating_set.filter(active=True)
        for activity in active_ratings.values_list('activity', flat=True):
            position = 'chair' if is_chair(user, activity, False) else 'leader'
            yield "{} {}".format(activity_name(activity), position)

    def leader_text(self, participant, user):
        return ', '.join(self.activity_descriptors(participant, user))

    @staticmethod
    def school(participant):
        """ Return what school participant goes to, if appliciable. """
        if not participant.is_student:
            return 'N/A'
        elif participant.affiliation in {'MU', 'MG'}:
            return 'MIT'
        else:
            return 'Other'  # We don't collect non-MIT affiliation

    def access_text(self, participant):
        """ Simple string indicating level of access person should have. """
        if self.discount.administrators.filter(pk=participant.pk).exists():
            return 'Admin'
        elif participant.is_leader:
            return 'Leader'
        elif participant.is_student:
            return 'Student'
        else:
            return 'Standard'

    @staticmethod
    def membership_status(user):
        """ Return membership status, irrespective of waiver status.

        (Companies don't care about participant waiver status, so ignore it).
        """
        # Status is one external query per user. Expensive! (We should refactor...)
        membership = geardb.user_membership_expiration(user)['membership']

        # We report Active/Expired, since companies don't care about waiver status
        if membership['active']:
            return 'Active'
        elif membership['expires']:
            return 'Expired {}'.format(membership['expires'].isoformat())
        else:
            return 'Missing'

    def get_row(self, participant, user):
        """ Get the row values that match the header for this discount sheet. """
        row_mapper = {
            self.labels.name: participant.name,
            self.labels.email: participant.email,
            self.labels.membership: self.membership_status(user),
            self.labels.student: participant.get_affiliation_display(),
            self.labels.school: self.school(participant)
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
    """ Add or update the participant.

    Much more efficient than updating the entire sheet.
    """
    user = models.User.objects.get(pk=participant.user_id)
    wks = gc.open_by_key(discount.ga_key).sheet1
    writer = SheetWriter(discount)

    # Attempt to find existing row, update it if found
    for cell in wks.findall(user.email):
        if cell.col == 2:  # (Participants _could_ name themselves an email...)
            start_cell = wks.get_addr_int(cell.row, 1)
            end_cell = wks.get_addr_int(cell.row, len(writer.header))
            cells = wks.range('{}:{}'.format(start_cell, end_cell))
            assign(cells, writer.get_row(participant, user))
            return

    # Insert a new row if no existing row found
    sorted_names = wks.col_values(1)[1:]
    row_index = bisect.bisect(sorted_names, participant.name) + 1
    wks.insert_row(writer.get_row(participant, user), row_index + 1)


@with_refreshed_token
def update_discount_sheet(discount):
    """ Update the entire worksheet, updating all members' status.

    This will remove members who no longer wish to share their information,
    so it's important to run this periodically.

    For individual updates, this approach should be avoided (instead, opting to
    update individual cells in the spreadsheet).
    """
    wks = gc.open_by_key(discount.ga_key).sheet1
    participants = list(discount.participant_set.order_by('name'))

    users = models.User.objects.filter(pk__in=[p.user_id for p in participants])
    user_by_id = {user.pk: user for user in users}

    writer = SheetWriter(discount)

    # Resize sheet to exact size, select all cells
    num_rows, num_cols = len(participants) + 1, len(writer.header)
    wks.resize(num_rows, num_cols)
    all_cells = wks.range('A1:{}'.format(wks.get_addr_int(num_rows, num_cols)))
    rows = grouper(all_cells, len(writer.header))

    assign(next(rows), writer.header)

    # Update each cell with current membership information
    for participant, row in zip(participants, rows):
        user = user_by_id[participant.user_id]
        assign(row, writer.get_row(participant, user))

    # Batch update to minimize API calls
    wks.update_cells(all_cells)
