"""
Functions for interacting with the gear database.
"""
from django.db import connections

from ws.utils.dates import local_now


def user_membership_expiration(user):
    if not user or user.is_anonymous():
        return None
    verified_emails = user.emailaddress_set.filter(verified=True)
    email_addresses = verified_emails.values_list('email', flat=True)
    return membership_expiration(email_addresses)


def membership_expiration(emails):
    cursor = connections['geardb'].cursor()
    ret = {'email': None, 'expires': None, 'active': False}
    if not emails:  # Passing an empty tuple will cause a SQL error
        return ret

    cursor.execute(
        """
        select p.email, max(pm.expires)
        from people_memberships pm
          join people p on p.id = pm.person_id
        where email in %s
        group by p.id, p.email
        """, [tuple(emails)]
    )
    membership = cursor.fetchone()
    if membership:
        ret['email'], ret['expires'] = membership
        ret['active'] = ret['expires'] >= local_now().date()
    return ret
