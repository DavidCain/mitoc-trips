"""
Functions for interacting with the gear database.

The gear database is itself a Django application (which we will eventually
integrate with this one). In the meantime, communicate with an
externally-hosted MySQL database instead of using Django models.
"""
import logging
import typing
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Iterator, List, Optional

from django.db import connections
from django.db.models import Case, Count, IntegerField, Sum, When
from django.db.models.functions import Lower
from mitoc_const import affiliations

from ws import models
from ws.utils.dates import local_date

logger = logging.getLogger(__name__)
# In all cases, we should use the MITOC Trips affiliation instead
DEPRECATED_GEARDB_AFFILIATIONS = {'Student'}


AFFILIATION_MAPPING = {aff.CODE: aff.VALUE for aff in affiliations.ALL}
# Deprecated statuses, but we can still map them
AFFILIATION_MAPPING['M'] = affiliations.MIT_AFFILIATE.VALUE
AFFILIATION_MAPPING['N'] = affiliations.NON_AFFILIATE.VALUE


class Rental(typing.NamedTuple):
    """ An object representing a rental by a user in the gear database. """

    email: str
    id: str  # Example, 'BK-19-04'
    name: str
    cost: float  # How much the daily cost for the item is
    checkedout: datetime
    overdue: bool


def verified_emails(user) -> List[str]:
    """ Return all email addresses that the user is verified to own. """
    if not (user and user.is_authenticated):
        return []
    emails = user.emailaddress_set
    return list(emails.filter(verified=True).values_list('email', flat=True))


def user_membership_expiration(user, try_cache=False):
    """ Return membership information for the user.

    If `try_cache` is True, then we'll first attempt to locate cached
    membership information. If any information exists, that will be returned.
    """
    if not (user and user.is_authenticated):
        return None
    if try_cache:
        participant = models.Participant.from_user(user, join_membership=True)
        if participant and participant.membership:
            return format_cached_membership(participant)

    return membership_expiration(verified_emails(user))


def repr_blank_membership():
    return {
        'membership': {'expires': None, 'active': False, 'email': None},
        'waiver': {'expires': None, 'active': False},
        'status': 'Missing',
    }


def membership_expiration(emails):
    """ Return the most recent expiration date for the given emails.

    The method is intended to allow looking up a single user's membership where
    they have multiple email addresses.

    It also calculates whether or not the membership has expired.
    """

    def expiration_date(info):
        mem_expires = info['membership']['expires']
        return (mem_expires is not None, mem_expires, *waiver_date(info))

    def waiver_date(info):
        waiver_expires = info['waiver']['expires']
        return (waiver_expires is not None, waiver_expires)

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
    # TODO: Should probably refactor this method so it doesn't have unclear side effects
    email = most_recent['membership']['email']
    participant = models.Participant.from_email(email)
    if participant:
        participant.update_membership(
            membership_expires=most_recent['membership']['expires'],
            waiver_expires=most_recent['waiver']['expires'],
        )

    return most_recent


def format_cached_membership(participant):
    """ Format a ws.models.Membership object as a server response. """
    mem = participant.membership
    return format_membership(
        participant.email, mem.membership_expires, mem.waiver_expires
    )


def format_membership(email, membership_expires, waiver_expires):
    person = repr_blank_membership()
    membership, waiver = person['membership'], person['waiver']
    membership['email'] = email

    for component, expires in [
        (membership, membership_expires),
        (waiver, waiver_expires),
    ]:
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


def matching_info_for(emails):
    """ Return all matching memberships under the email addresses.

    Most participants will have just one membership, but some people may have
    multiple memberships! These memberships should be merged on the gear
    database side, but we must handle them all the same.
    """
    if not emails:  # Passing an empty tuple will cause a SQL error
        return

    cursor = connections['geardb'].cursor()

    # Get the most recent membership and most recent waiver per email
    # It's possible the user has a newer waiver under another email address,
    # but this is what the gear database reports (and we want consistency)
    cursor.execute(
        '''
        select p.id as person_id,
               p.affiliation,
          date(p.date_inserted) as date_inserted,
               lower(p.email),
               lower(pe.alternate_email),
               max(pm.expires)  as membership_expires,
          date(max(pw.expires)) as waiver_expires
          from people p
               left join geardb_peopleemails pe on p.id = pe.person_id
               left join people_memberships  pm on p.id = pm.person_id
               left join people_waivers      pw on p.id = pw.person_id
         where p.email in %(emails)s
            or pe.alternate_email in %(emails)s
         group by p.id, p.affiliation, p.email, pe.alternate_email
         order by membership_expires, waiver_expires
        ''',
        {'emails': tuple(emails)},
    )

    # Email capitalization in the database may differ from what users report
    # Map back to the case supplied in arguments for easier mapping
    to_original_case = {email.lower(): email for email in emails}

    for (
        person_id,
        affiliation,
        date_inserted,
        main,
        alternate,
        m_expires,
        w_expires,
    ) in cursor:
        # We know that the either the main or alternate email was requested
        # (It's possible that membership records were requested for _both_ emails)
        # In case the alternate email was given alongside the primary email,
        # always give preference to the primary email.
        email = main if main in to_original_case else alternate

        yield {
            'person_id': person_id,
            'affiliation': affiliation,
            'date_inserted': date_inserted,
            'email': to_original_case[email],
            'membership_expires': m_expires,
            'waiver_expires': w_expires,
        }


def _yield_matches(emails):
    """ For each given email, yield a record about the person (if found).

    - The email addresses may or may not correspond to the same person.
    - Some email addresses may return the same membership record
    """
    for info in matching_info_for(emails):
        formatted = format_membership(
            info['email'], info['membership_expires'], info['waiver_expires']
        )
        yield info['email'], formatted


def matching_memberships(emails):
    """ Return the most current membership found for each email in the list.

    This method is used in two key ways:
    - Look up membership records for a single person, under all their emails
    - Look up memberships for many participants, under all their emails
    """
    return OrderedDict(_yield_matches(emails))


def outstanding_items(
    emails: List[str], rented_on_or_before: Optional[datetime] = None
) -> Iterator[Rental]:
    """ Yield all items that are currently checked out to the members.

    This method supports listing items for an individual participant (who may
    have multiple emails/gear accounts) as well as all participants on a trip.
    """
    if not emails:
        return

    # Email capitalization in the database may differ from what users report
    # Map back to the case supplied in arguments for easier mapping
    to_original_case = {email.lower(): email for email in emails}

    cursor = connections['geardb'].cursor()

    rental_date_clause = ''
    if rented_on_or_before:
        rental_date_clause = 'and checkedout <= %(rented_on_or_before)s'

    cursor.execute(
        f'''
        select lower(p.email),
               -- Using proper array types here would be nice, but MySQL lacks them...
               group_concat(distinct lower(pe.alternate_email) separator ','),
               g.id,
               gt.type_name,
               gt.rental_amount,
               date(convert_tz(r.checkedout, '+00:00', '-05:00')) as checkedout
          from rentals          r
               join people      p on p.id = r.person_id
               join gear        g on g.id = r.gear_id
               join gear_types gt on g.type = gt.id
               left join geardb_peopleemails pe on p.id = pe.person_id
         where r.returned is null
           {rental_date_clause}
           and (p.email in %(emails)s or pe.alternate_email in %(emails)s)
           -- It's possible for there to be extra alternate email records matching the primary email
           -- Omit these so we don't get needless duplicates
           and (pe.alternate_email is null or p.email != pe.alternate_email)
         group by p.email, g.id, gt.type_name, gt.rental_amount, r.checkedout
        ''',
        {'emails': tuple(emails), 'rented_on_or_before': rented_on_or_before},
    )

    for main, alternate_emails, gear_id, name, cost, checkedout in cursor.fetchall():
        if main in to_original_case:
            email = main
        else:
            # Because either main or alternate email were matched, this should never happen.
            assert alternate_emails, "Alternate emails were unexpectedly empty!"
            alternates = alternate_emails.split(',')
            try:
                email = next(e for e in alternates if e in to_original_case)
            except StopIteration:
                # This method is a generator - raising StopIteration would stop iteration
                raise ValueError("Expected at least one email to match!")

        yield Rental(
            email=to_original_case[email],
            id=gear_id,
            name=name,
            cost=cost,
            checkedout=checkedout,
            overdue=(local_date() - checkedout > timedelta(weeks=10)),
        )


def user_rentals(user) -> List[Rental]:
    return list(outstanding_items(verified_emails(user)))


def update_affiliation(participant):
    """ Update the gear db if the affiliation of a participant has changed.

    This is useful in three scenarios:
    - Affiliation changes via a self-reported update
    - A participant states their affiliation without a membership
    - We have affiliation data in the trips db that the gear db lacks

    The Trips database collects affiliations from its users more often than the
    gear database. We request that participants update their information at least
    once every 6 months (settings.MUST_UPDATE_AFTER_DAYS), but the gear database
    only gets affiliation information every time a participant renews their
    membership.

    At time of writing, we also allow MIT students to go on some trips with
    just a waiver (and no membership). For tracking purposes, we still want to
    know their affiliation, but we'll have no data from membership renewals.

    Finally, the gear database has not always collected affiliation data at
    the same level of granularity as the trips database. This method can sync
    affiliation data to the gear database that it previously lacked.
    """
    if participant.affiliation == 'S':
        # Deprecated status, participant hasn't logged on in years
        return

    emails = models.EmailAddress.objects.filter(
        verified=True, user_id=participant.user_id
    ).values_list('email', flat=True)
    matches = list(matching_info_for(emails))
    if not matches:
        return

    def last_updated_dates(info):
        """ Yield the date (not timestamp!) of various updates. """
        if info['membership_expires']:
            yield info['membership_expires'] - timedelta(days=365)
        if info['waiver_expires']:
            yield info['waiver_expires'] - timedelta(days=365)
        if info['date_inserted']:  # Null for a few users!
            yield info['date_inserted']

    def last_updated(info):
        """ Use the membership that was most recently updated. """
        dates = list(last_updated_dates(info))
        return max(dates) if dates else datetime.min.date()

    most_recent = max(matches, key=last_updated)

    geardb_affiliation = AFFILIATION_MAPPING[participant.affiliation]

    # If the database already has the same affiliation, no need to update
    if geardb_affiliation == most_recent['affiliation']:
        return

    # We update in a few conditions:
    # - the person has an affiliation that's less specific than this one
    # - the gear database has no known affiliation
    # - the affiliation was updated more recently than the gear database
    should_update = (
        most_recent['affiliation'] in DEPRECATED_GEARDB_AFFILIATIONS
        or not most_recent['affiliation']
        or participant.profile_last_updated.date() >= last_updated(most_recent)
    )

    if should_update:
        cursor = connections['geardb'].cursor()
        logger.info(
            "Updating affiliation for %s from %s to %s",
            participant.name,
            most_recent['affiliation'],
            geardb_affiliation,
        )
        cursor.execute(
            '''
            update people
               set affiliation = %(affiliation)s
             where id = %(person_id)s
            ''',
            {'affiliation': geardb_affiliation, 'person_id': most_recent['person_id']},
        )


def all_active_members():
    """ Yield emails and rental activity for all members with current dues. """
    cursor = connections['geardb'].cursor()
    cursor.execute(
        '''
        -- NOTE: Will have one or more rows per active member
        select p.id as person_id,
               coalesce(p.affiliation, 'Unknown') as last_known_affiliation,
               lower(p.email) as email,
               lower(pe.alternate_email) as alternate_email,
               count(r.id) as num_rentals
          from people p
               join people_memberships       pm on p.id = pm.person_id
               left join geardb_peopleemails pe on p.id = pe.person_id
               left join rentals             r  on p.id = r.person_id
         where pm.expires > now()
         group by p.id, p.affiliation, p.email, pe.alternate_email
        '''
    )

    for person_id, affiliation, main, alternate_email, num_rentals in cursor.fetchall():
        known_emails = (e for e in (main, alternate_email) if e)
        for email in known_emails:
            info = {
                # NOTE: Anyone with >1 alternate email will have multiple rows!
                # (We'll use multiple emails to look up). Ensure we enforce uniqueness
                'person_id': person_id,
                'last_known_affiliation': affiliation,
                'num_rentals': num_rentals,
            }
            yield email, info


def trips_information():
    """ Give important counts, indexed by user IDs.

    Each participant has a singular underlying user. This user has one or more
    email addresses, which form the link back to the gear database.
    The user database lives separately from the participant database, so we'll
    need to make a separate query for user information anyway.
    """
    # TODO: Last year only?
    signup_on_trip = Case(
        When(signup__on_trip=True, then=1), default=0, output_field=IntegerField()
    )

    trips_per_participant = dict(
        models.Participant.objects.all()
        .annotate(
            # NOTE: Adding other annotations results in double-counting signups
            # (We do multiple JOINs, and can't easily pass a DISTINCT to the Sum)
            num_trips_attended=Sum(signup_on_trip)
        )
        .values_list('pk', 'num_trips_attended')
    )

    additional_stats = (
        models.Participant.objects.all()
        .annotate(
            num_discounts=Count('discounts', distinct=True),
            num_trips_led=Count('trips_led', distinct=True),
        )
        .values_list('pk', 'user_id', 'num_discounts', 'num_trips_led')
    )

    for (pk, user_id, num_discounts, num_trips_led) in additional_stats:
        info = {
            'num_trips_attended': trips_per_participant[pk],
            'num_trips_led': num_trips_led,
            'num_discounts': num_discounts,
        }
        yield user_id, info


def membership_information():
    """ All current active members, annotated with additional info.

    For each paying member, we also mark if they:
    - have attended any trips
    - have led any trips
    - have rented gear
    - make use MITOC discounts
    """
    # Get trips information indexed by Trips user ID's
    info_by_user_id = dict(trips_information())

    # Bridge from a lowercase email address to a Trips user ID
    email_to_user_id = dict(
        models.EmailAddress.objects.filter(verified=True)
        .annotate(lower_email=Lower('email'))
        .values_list('lower_email', 'user_id')
    )

    def trips_info_for(email):
        try:
            user_id = email_to_user_id[email]
        except KeyError:  # No Trips account
            return {}

        try:
            return info_by_user_id[user_id]
        except KeyError:  # User, but no corresponding Participant
            return {}

    # Map from the gear database's person ID to stats about the member
    all_members = {}

    for email, info in all_active_members():
        existing_record = all_members.get(info['person_id'])

        if existing_record:
            # We already recorded them as a member, don't report twice
            # However, we might only have trips info under an alternate email
            existing_record.update(trips_info_for(email))
            continue

        all_members[info['person_id']] = {
            'last_known_affiliation': info['last_known_affiliation'],
            'num_rentals': info['num_rentals'],
            **trips_info_for(email),
        }
    return all_members
