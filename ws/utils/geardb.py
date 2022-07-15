"""
Functions for interacting with the gear database.

The gear database is itself a Django application (which we are in the processes
of integrating with this one via an API layer).

In the meantime, this module contains some direct database access to an
externally-hosted MySQL database.
"""
import logging
from datetime import date, datetime, timedelta
from typing import (
    Any,
    Dict,
    Iterable,
    Iterator,
    List,
    Literal,
    NamedTuple,
    Optional,
    Tuple,
    TypedDict,
)
from urllib.parse import urljoin

import requests
from django.db import connections
from django.db.models import Case, Count, IntegerField, Sum, When

from ws import models, settings
from ws.utils import api as api_util
from ws.utils.dates import local_date

logger = logging.getLogger(__name__)


API_BASE = 'https://mitoc-gear.mit.edu/'

JsonDict = Dict[str, Any]


Status = Literal[
    "Missing",
    "Missing Waiver",
    "Waiver Expired",
    "Active",
    "Missing Membership",
    "Expired",
]


class _OnlyMembershipDict(TypedDict):
    expires: Optional[date]
    active: bool
    email: Optional[str]


class _OnlyWaiverDict(TypedDict):
    expires: Optional[date]
    active: bool


class MembershipDict(TypedDict):
    membership: _OnlyMembershipDict
    waiver: _OnlyWaiverDict
    status: Status


class TripsInformation(NamedTuple):
    num_trips_attended: int
    num_trips_led: int
    num_discounts: int


class MembershipInformation(NamedTuple):
    person_id: int
    last_known_affiliation: str
    num_rentals: int

    trips_information: Optional[TripsInformation]


def gear_bearer_jwt(**payload) -> str:
    """Express a JWT for use on mitoc-gear.mit.edu as a bearer token.

    The API there expects a token signed with a shared key - without this token,
    authorized routes will be denied access.
    """
    return api_util.bearer_jwt(settings.GEARDB_SECRET_KEY, **payload)


def query_api(route: str, **params: Any) -> List[JsonDict]:
    """Request results from the API on mitoc-gear.mit.edu."""
    response = requests.get(
        urljoin(API_BASE, route),
        timeout=5,
        # NOTE: We sign the payload here, even though current implementations only use query params.
        # This does technically mean that anyone with a valid token can use the token to query any data.
        # However, tokens aren't given to end users, only used on the systems which already have the secret.
        headers={'Authorization': gear_bearer_jwt(**params)},
        params=params,
    )
    response.raise_for_status()

    body = response.json()
    results: List[JsonDict] = body['results']

    if body['next']:
        logger.error(
            "Results are paginated; this is not expected or handled. "
            "(%s / %s results), URL: %s, Next: %s",
            len(results),
            body['count'],
            response.url,
            body['next'],
        )

    return results


class Rental(NamedTuple):
    """An object representing a rental by a user in the gear database."""

    email: str
    id: str  # Example, 'BK-19-04'
    name: str
    cost: float  # How much the daily cost for the item is
    checkedout: date
    overdue: bool


def verified_emails(user) -> List[str]:
    """Return all email addresses that the user is verified to own.

    We should only ever report results for email addresses we know the user controls.
    """
    if not (user and user.is_authenticated):
        return []
    emails = user.emailaddress_set
    return sorted(emails.filter(verified=True).values_list('email', flat=True))


def query_geardb_for_membership(user: models.User) -> Optional[MembershipDict]:
    """Ask the gear database for the latest information, bypassing any caches."""
    assert user.is_authenticated

    emails = verified_emails(user)
    if not emails:
        logger.error("Cannot query for user without verified emails")
        return None

    results = query_api('/api-auth/v1/membership_waiver/', email=emails)
    if not results:
        return repr_blank_membership()

    assert len(results) == 1, "Unexpectedly got multiple members!"
    result = results[0]

    def expiration_from_payload(json_dict: JsonDict) -> Optional[date]:
        if 'expires' not in json_dict:
            return None
        return date.fromisoformat(json_dict['expires'])

    return _format_membership(
        result.get('email', None),
        expiration_from_payload(result['membership']),
        expiration_from_payload(result['waiver']),
    )


def repr_blank_membership() -> MembershipDict:
    return {
        'membership': {'expires': None, 'active': False, 'email': None},
        'waiver': {'expires': None, 'active': False},
        'status': 'Missing',
    }


def _format_cached_membership(participant: models.Participant) -> MembershipDict:
    """Format a ws.models.Membership object as a server response."""
    mem = participant.membership
    assert mem is not None
    return _format_membership(
        participant.email, mem.membership_expires, mem.waiver_expires
    )


def _represent_status(
    membership: _OnlyMembershipDict,
    waiver: _OnlyWaiverDict,
) -> Status:
    """Generate a human-readable status (for use in the UI)."""
    if not membership['active']:
        return "Missing Membership" if waiver['active'] else "Expired"

    if not waiver['expires']:
        return "Missing Waiver"
    if not waiver['active']:
        return "Waiver Expired"
    return "Active"


def _format_membership(
    email: Optional[str],
    membership_expires: Optional[date],
    waiver_expires: Optional[date],
) -> MembershipDict:
    person = repr_blank_membership()
    membership, waiver = person['membership'], person['waiver']
    membership['email'] = email

    for component, expires in [
        (membership, membership_expires),
        (waiver, waiver_expires),
    ]:
        component['expires'] = expires
        component['active'] = bool(expires and expires >= local_date())

    person['status'] = _represent_status(membership, waiver)

    return person


def _matching_info_for(emails):
    """Return all matching memberships under the email addresses.

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


def matching_memberships(emails: Iterable[str]) -> Dict[str, MembershipDict]:
    """Return the most current membership found for each email in the list.

    This method is used in two key ways:
    - Look up membership records for a single person, under all their emails
    - Look up memberships for many participants, under all their emails
    """

    def _yield_matches():
        """For each given email, yield a record about the person (if found).

        - The email addresses may or may not correspond to the same person.
        - Some email addresses may return the same membership record
        """
        for info in _matching_info_for(emails):
            formatted = _format_membership(
                info['email'], info['membership_expires'], info['waiver_expires']
            )
            yield info['email'], formatted

    return dict(_yield_matches())


def outstanding_items(emails: List[str]) -> Iterator[Rental]:
    """Return all items that are currently checked out to one or more members.

    This method supports listing items for an individual participant (who may
    have multiple emails/gear accounts) as well as all participants on a trip.
    """
    if not emails:
        return

    # Email capitalization in the database may differ from what users report
    # The gear database does case-insensitive lookups.
    # We wish to preserve association back to the originally-supplied emails.
    #
    # NOTE: There is a possible exploit here where a user can use special Unicode characters
    # in order to fetch the gear rental history for another user.
    # For example:
    # - victim is kate@example.com
    # - attacker registers Kate@example.com (0x212A *not* the ASCII K)
    # We don't guard against this exploit here, but can flag which users try to register malicious emails.
    # Additionally, we only report results to users who have verified email addresses,
    # and MIT/Gmail/other email providers generally prevent registering emails with these colliding chars.
    #
    # More info: https://eng.getwisdom.io/hacking-github-with-unicode-dotless-i/
    to_original_case = {email.lower(): email for email in emails}

    today = local_date()

    for result in query_api('api-auth/v1/rentals/', email=emails):  # One row per item
        person, gear = result['person'], result['gear']

        # Map from the person record back to the requested email address
        all_known_emails: List[str] = [person['email'], *person['alternate_emails']]
        try:
            email = next(e for e in all_known_emails if e.lower() in to_original_case)
        except StopIteration as err:
            # We should never get a result for a user whose email was not queried
            raise ValueError("Expected at least one email to match!") from err

        checkout_date = datetime.fromisoformat(result['checkedout']).date()
        yield Rental(
            email=to_original_case[email.lower()],
            id=gear['id'],
            name=gear['type']['type_name'],
            cost=float(gear['type']['rental_amount']),
            checkedout=checkout_date,
            overdue=(today - checkout_date > timedelta(weeks=10)),
        )


def user_rentals(user) -> List[Rental]:
    """Return items which the user has rented (which can be reported to that user).

    It's very, very important that these emails be *verified*.
    This guards against users trying to spoof other users to identify their rentals.

    Email verification also provides a (small) layer of defense against case
    collision attacks where an attacker can register a similar email address
    which lowercases down to a victim's email.
    """
    return list(outstanding_items(verified_emails(user)))


def update_affiliation(participant: models.Participant) -> Optional[requests.Response]:
    """Update the gear db if the affiliation of a participant has changed.

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
        return None

    all_verified_emails = models.EmailAddress.objects.filter(
        verified=True, user_id=participant.user_id
    ).values_list('email', flat=True)

    other_verified_emails = set(all_verified_emails) - {participant.email}

    payload = {
        'email': participant.email,
        'affiliation': participant.affiliation,
        'other_verified_emails': sorted(other_verified_emails),
    }
    response = requests.put(
        urljoin(API_BASE, 'api-auth/v1/affiliation/'),
        # NOTE: We sign the payload here, even though current implementations just use the body.
        # This does technically mean that anyone with a valid token can use the token to query any data.
        # However, tokens aren't given to end users, only used on the systems which already have the secret.
        headers={'Authorization': gear_bearer_jwt(**payload)},
        json=payload,
    )
    # Note that this may be a 400!
    return response


def trips_information() -> Dict[int, TripsInformation]:
    """Give important counts, indexed by user IDs.

    Each participant has a singular underlying user. This user has one or more
    email addresses, which form the link back to the gear database.
    The user database lives separately from the participant database, so we'll
    need to make a separate query for user information anyway.
    """
    # TODO: Last year only?
    signup_on_trip = Case(
        When(signup__on_trip=True, then=1), default=0, output_field=IntegerField()
    )

    trips_per_participant: Dict[int, int] = dict(
        models.Participant.objects.all()
        .annotate(
            # NOTE: Adding other annotations results in double-counting signups
            # (We do multiple JOINs, and can't easily pass a DISTINCT to the Sum)
            num_trips_attended=Sum(signup_on_trip)
        )
        .values_list('pk', 'num_trips_attended')
    )

    additional_stats: Iterable[Tuple[int, int, int, int]] = (
        models.Participant.objects.all()
        .annotate(
            num_discounts=Count('discounts', distinct=True),
            num_trips_led=Count('trips_led', distinct=True),
        )
        .values_list('pk', 'user_id', 'num_discounts', 'num_trips_led')
    )

    return {
        user_id: TripsInformation(
            num_trips_attended=trips_per_participant[pk],
            num_trips_led=num_trips_led,
            num_discounts=num_discounts,
        )
        for (pk, user_id, num_discounts, num_trips_led) in additional_stats
    }


# NOTE: This method is only used for the (leaders-only, hacky, `/stats` endpoint)
def membership_information() -> Dict[int, MembershipInformation]:
    """All current active members, annotated with additional info.

    For each paying member, we also mark if they:
    - have attended any trips
    - have led any trips
    - have rented gear
    - make use MITOC discounts
    """
    info_by_user_id = trips_information()  # pylint: disable=unused-variable

    # This method should soon be replaced by an API call to mitoc-gear
    return {}
