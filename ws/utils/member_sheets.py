"""
Allows maintenance of Google Spreadsheets with membership information.

Users can opt-in to have their information shared with third parties.

These methods will post information about users' membership status to Google
spreadsheets. Each spreadsheet will be shared with the company offering the
discount, so that they can verify membership status.
"""
import bisect
from itertools import izip_longest
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
    return izip_longest(*args, fillvalue=fillvalue)


class SheetWriter(object):
    """ Utility methods for formatting a row in discount worksheets. """
    def __init__(self, discount):
        self.discount = discount

        self.header = ['Name', 'Email', 'Membership Status']
        if self.discount.report_leader:
            self.header.append('Leader Status')
        if self.discount.student_required:
            self.header.append('Student Status')

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
            'Name': participant.name,
            'Email': participant.email,
            'Membership Status': self.membership_status(user),
            'Student Status': participant.get_affiliation_display()
        }
        if 'Leader Status' in self.header:  # Only fetch if needed
            row_mapper['Leader Status'] = self.leader_text(participant, user)

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

    assign(rows.next(), writer.header)

    # Update each cell with current membership information
    for participant, row in zip(participants, rows):
        user = user_by_id[participant.user_id]
        assign(row, writer.get_row(participant, user))

    # Batch update to minimize API calls
    wks.update_cells(all_cells)
