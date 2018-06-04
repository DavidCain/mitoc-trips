"""
Functions for interacting with the gear database.

The gear database is itself a Django application (which we will eventually
integrate with this one). In the meantime, communicate with an
externally-hosted MySQL database instead of using Django models.
"""
from collections import OrderedDict
from datetime import timedelta

from django.db import connections

from ws.utils.dates import local_date
from ws import models


def verified_emails(user):
    if not user or user.is_anonymous:
        return []
    emails = user.emailaddress_set
    return emails.filter(verified=True).values_list('email', flat=True)


def user_membership_expiration(user, try_cache=False):
    """ Return membership information for the user.

    If `try_cache` is True, then we'll first attempt to locate cached
    membership information. if any information exists, that will be returned.
    """
    if not user or user.is_anonymous:
        return None
    if try_cache:
        participant = models.Participant.from_user(user, join_membership=True)
        if participant and participant.membership:
            return format_cached_membership(participant)

    return membership_expiration(verified_emails(user))


def repr_blank_membership():
    return {'membership': {'expires': None, 'active': False, 'email': None},
            'waiver': {'expires': None, 'active': False},
            'status': 'Missing'}


def membership_expiration(emails):
    """ Return the most recent expiration date for the given emails.

    The method is intended to allow looking up a single user's membership where
    they have multiple email addresses.

    It also calculates whether or not the membership has expired.
    """
    def expiration_date(info):
        return (info['membership']['expires'], info['waiver']['expires'])

    def waiver_date(info):
        return info['waiver']['expires']

    # Find all memberships under one or more of the participant's emails
    memberships_by_email = matching_memberships(emails)
    if not memberships_by_email:
        return repr_blank_membership()

    # The most recent account should be considered as their one membership
    most_recent = max(memberships_by_email.values(), key=expiration_date)

    # If there's an older membership with an active waiver, use that!
    if not most_recent['membership']['active']:
        last_waiver = max(memberships_by_email.values(), key=waiver_date)
        if last_waiver['waiver']['active']:
            most_recent = last_waiver

    # Since we fetched the most current information from the db, update cache
    email = most_recent['membership']['email']
    participant = models.Participant.from_email(email)
    if participant:
        participant.update_membership(
            membership_expires=most_recent['membership']['expires'],
            waiver_expires=most_recent['waiver']['expires']
        )

    return most_recent


def format_cached_membership(participant):
    """ Format a ws.models.Membership object as a server response. """
    mem = participant.membership
    return format_membership(participant.email,
                             mem.membership_expires, mem.waiver_expires)


def format_membership(email, membership_expires, waiver_expires):
    person = repr_blank_membership()
    membership, waiver = person['membership'], person['waiver']
    membership['email'] = email

    for component, expires in [(membership, membership_expires),
                               (waiver, waiver_expires)]:
        component['expires'] = expires
        component['active'] = bool(expires and expires >= local_date())

    # Generate a human-readable status
    if membership['active']:  # Membership is active and up-to-date
        if not waiver['expires']:
            status = "Missing Waiver"
        elif not waiver['active']:
            status = "Waiver Expired"
        else:
            status = "Active"
    else:
        status = "Missing Membership" if waiver['active'] else "Expired"

    person['status'] = status

    return person


def matching_memberships(emails):
    """ Return the most current membership found for each email in the list.

    Newer memberships will appear earlier in the results.
    """
    if not emails:  # Passing an empty tuple will cause a SQL error
        return OrderedDict()

    cursor = connections['geardb'].cursor()

    # Get the most recent membership and most recent waiver per email
    # It's possible the user has a newer waiver under another email address,
    # but this is what the gear database reports (and we want consistency)
    cursor.execute(
        '''
        select lower(p.email),
               max(pm.expires)  as membership_expires,
          date(max(pw.expires)) as waiver_expires
          from people p
               left join people_memberships pm on p.id = pm.person_id
               left join people_waivers     pw on p.id = pw.person_id
         where p.email in %s
         group by p.email
         order by membership_expires, waiver_expires
        ''', [tuple(emails)]
    )

    # Email capitalization in the database may differ from what users report
    # Map back to the case supplied in arguments for easier mapping
    original_case = {email.lower(): email for email in emails}
    matches = ((original_case[email], m_expires, w_expires)
               for (email, m_expires, w_expires) in cursor.fetchall())

    return OrderedDict((email, format_membership(email, m_expires, w_expires))
                       for (email, m_expires, w_expires) in matches)


def outstanding_items(emails):
    if not emails:
        return []
    cursor = connections['geardb'].cursor()
    cursor.execute(
        '''
        select g.id, gt.type_name, gt.rental_amount,
               date(convert_tz(r.checkedout, '+00:00', '-05:00')) as checkedout
          from rentals  r
               join gear g on g.id = r.gear_id
               join gear_types gt on gt.id = g.type
         where returned is null
           and person_id in (select id from people where email in %s)
        ''', [tuple(emails)])
    items = [{'id': gear_id, 'name': name, 'cost': cost, 'checkedout': checkedout}
             for gear_id, name, cost, checkedout in cursor.fetchall()]
    for item in items:
        item['overdue'] = local_date() - item['checkedout'] > timedelta(weeks=10)
    return items


def user_rentals(user):
    return outstanding_items(verified_emails(user))
