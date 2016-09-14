"""
Functions for interacting with the gear database.

The gear database is itself a Django application (which we will eventually
integrate with this one). In the meantime, communicate with an
externally-hosted MySQL database instead of using Django models.
"""
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


def membership_expiration(emails):
    """ Return the most recent expiration date for the given emails.

    The method is intended to allow looking up a single user's membership where
    they have multiple email addresses.

    It also calculates whether or not the membership has expired.
    """
    cursor = connections['geardb'].cursor()

    membership = {'expires': None, 'active': False, 'email': None}
    waiver = {'expires': None, 'active': False}
    person = {'membership': membership, 'waiver': waiver, 'status': 'Missing'}
    if not emails:  # Passing an empty tuple will cause a SQL error
        return person

    # Get the most recent membership and most recent waiver per email
    # It's possible the user has a newer waiver under another email address,
    # but this is what the gear database reports (and we want consistency)
    cursor.execute(
        """
        select p.email,
               max(pm.expires)  as membership_expires,
          date(max(pw.expires)) as waiver_expires
        from people_memberships pm
               join people p          on p.id = pm.person_id
          left join people_waivers pw on p.id = pw.person_id
        where p.email in %s
        group by p.email
        order by membership_expires desc
        limit 1
        """, [tuple(emails)]
    )
    row = cursor.fetchone()
    if not row:  # No membership on file (might have signed a waiver, though)
        return person

    membership['email'], membership['expires'], waiver['expires'] = row
    for component in [membership, waiver]:
        expires = component['expires']
        component['active'] = expires and expires >= local_date()

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


def outstanding_items(emails):
    if not emails:
        return None
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