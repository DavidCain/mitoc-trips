"""
Functions for interacting with the gear database.

The gear database is itself a Django application (which we will eventually
integrate with this one). In the meantime, communicate with an
externally-hosted MySQL database instead of using Django models.
"""
from collections import OrderedDict
from datetime import timedelta

from django.db import connections

from ws.utils.dates import local_now, local_date


def verified_emails(user):
    if not user or user.is_anonymous():
        return []
    emails = user.emailaddress_set
    return emails.filter(verified=True).values_list('email', flat=True)


def user_membership_expiration(user):
    if not user or user.is_anonymous():
        return None
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
    # First membership matching will be the most current
    matches = matching_memberships(emails)
    return matches.values()[-1] if matches else repr_blank_membership()


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
        status = "Expired"

    person['status'] = status

    return person


def matching_memberships(emails):
    """ Return the most current membership found for each email in the list.

    Newer memberships will appear earlier in the results.
    """
    cursor = connections['geardb'].cursor()

    if not emails:  # Passing an empty tuple will cause a SQL error
        return OrderedDict()

    # Get the most recent membership and most recent waiver per email
    # It's possible the user has a newer waiver under another email address,
    # but this is what the gear database reports (and we want consistency)
    cursor.execute(
        """
        select lower(p.email),
               max(pm.expires)  as membership_expires,
          date(max(pw.expires)) as waiver_expires
        from people_memberships pm
               join people p          on p.id = pm.person_id
          left join people_waivers pw on p.id = pw.person_id
        where p.email in %s
        group by p.email
        -- importantly, we put most current memberships last in the query
        -- (other areas of the app will assume this)
        order by membership_expires
        """, [tuple(emails)]
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
        """
        select g.id, gt.type_name, gt.rental_amount, r.checkedout
        from rentals  r
          join gear g on g.id = r.gear_id
          join gear_types gt on gt.id = g.type
        where returned is null
          and person_id in (select id from people where email in %s)
        """, [tuple(emails)])
    items = [{'id': gear_id, 'name': name, 'cost': cost, 'checkedout': checkedout}
             for gear_id, name, cost, checkedout in cursor.fetchall()]
    for item in items:
        item['overdue'] = local_now() - item['checkedout'] > timedelta(weeks=10)
    return items


def user_rentals(user):
    return outstanding_items(verified_emails(user))
