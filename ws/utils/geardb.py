"""Functions for interacting with the gear database.

The gear database is itself a Django application, which we interface with
via machine-to-machine API endpoints.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import urljoin

import requests
from allauth.account.models import EmailAddress

from ws import models, settings
from ws.utils import api as api_util
from ws.utils.dates import local_date

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


API_BASE = "https://mitoc-gear.mit.edu/"

JsonDict = dict[str, Any]


class MembershipWaiver(NamedTuple):
    """Light wrapper type around response to /api-auth/v1/membership_waiver/"""

    email: str | None
    membership_expires: date | None
    waiver_expires: date | None


class Rental(NamedTuple):
    """An object representing a rental by a user in the gear database.

    Light wrapper type around response to api-auth/v1/rentals/
    """

    email: str
    id: str  # Example, 'BK-19-04'
    name: str
    cost: float  # How much the daily cost for the item is
    checkedout: date
    overdue: bool


class TripsInformation(NamedTuple):
    is_leader: bool
    num_trips_attended: int
    num_trips_led: int
    num_discounts: int
    # Email address as given on Participant object
    # (We assume this is their preferred current email)
    email: str


class MembershipInformation(NamedTuple):
    email: str
    alternate_emails: list[str]
    person_id: int
    affiliation: str
    num_rentals: int

    trips_information: TripsInformation | None


def gear_bearer_jwt(**payload: Any) -> str:
    """Express a JWT for use on mitoc-gear.mit.edu as a bearer token.

    The API there expects a token signed with a shared key - without this token,
    authorized routes will be denied access.
    """
    return api_util.bearer_jwt(settings.GEARDB_SECRET_KEY, **payload)


def query_api(route: str, **params: Any) -> list[JsonDict]:
    """Request results from the API on mitoc-gear.mit.edu."""
    response = requests.get(
        urljoin(API_BASE, route),
        timeout=5,
        # NOTE: We sign the payload here, even though current implementations only use query params.
        # This does technically mean that anyone with a valid token can use the token to query any data.
        # However, tokens aren't given to end users, only used on the systems which already have the secret.
        headers={"Authorization": gear_bearer_jwt(**params)},
        params=params,
    )
    response.raise_for_status()

    body = response.json()
    # If pagination class is none, we'll just return a list as-is.
    if isinstance(body, list):
        return body

    results: list[JsonDict] = body["results"]
    if body["next"]:
        logger.error(
            "Results are paginated; this is not expected or handled. "
            "(%s / %s results), URL: %s, Next: %s",
            len(results),
            body["count"],
            response.url,
            body["next"],
        )

    return results


def _verified_emails(user: User) -> list[str]:
    """Return all email addresses that the user is verified to own.

    We should only ever report results for email addresses we know the user controls.
    """
    if not (user and user.is_authenticated):
        return []
    # (This relation is added by django-allauth, but django-stubs/mypy can't tell)
    emails = user.emailaddress_set  # type: ignore[attr-defined]
    return sorted(emails.filter(verified=True).values_list("email", flat=True))


def query_geardb_for_membership(user: User) -> MembershipWaiver | None:
    """Ask the gear database for the latest information, bypassing any caches."""
    assert user.is_authenticated

    emails = _verified_emails(user)
    if not emails:
        logger.error("Cannot query for user without verified emails")
        return None

    results = query_api("/api-auth/v1/membership_waiver/", email=emails)
    if not results:
        # This is substantively different from a null result.
        # Rather, it's a *successful* query -- no member found.
        return MembershipWaiver(
            email=None,
            membership_expires=None,
            waiver_expires=None,
        )

    assert len(results) == 1, "Unexpectedly got multiple members!"
    result = results[0]

    def expiration_from_payload(json_dict: JsonDict) -> date | None:
        if "expires" not in json_dict:
            return None
        return date.fromisoformat(json_dict["expires"])

    return MembershipWaiver(
        result.get("email") or None,  # (Blank emails can be returned)
        expiration_from_payload(result["membership"]),
        expiration_from_payload(result["waiver"]),
    )


def outstanding_items(emails: list[str]) -> Iterator[Rental]:
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

    for result in query_api("api-auth/v1/rentals/", email=emails):  # One row per item
        person, gear = result["person"], result["gear"]

        # Map from the person record back to the requested email address
        all_known_emails: list[str] = [person["email"], *person["alternate_emails"]]
        try:
            email = next(e for e in all_known_emails if e.lower() in to_original_case)
        except StopIteration as err:
            # We should never get a result for a user whose email was not queried
            raise ValueError("Expected at least one email to match!") from err

        checkout_date = datetime.fromisoformat(result["checkedout"]).date()
        yield Rental(
            email=to_original_case[email.lower()],
            id=gear["id"],
            name=gear["type"]["type_name"],
            cost=float(gear["type"]["rental_amount"]),
            checkedout=checkout_date,
            overdue=(today - checkout_date > timedelta(weeks=10)),
        )


def user_rentals(user: User) -> list[Rental]:
    """Return items which the user has rented (which can be reported to that user).

    It's very, very important that these emails be *verified*.
    This guards against users trying to spoof other users to identify their rentals.

    Email verification also provides a (small) layer of defense against case
    collision attacks where an attacker can register a similar email address
    which lowercases down to a victim's email.
    """
    return list(outstanding_items(_verified_emails(user)))


def update_affiliation(participant: models.Participant) -> requests.Response | None:
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
    if participant.affiliation == "S":
        # Deprecated status, participant hasn't logged on in years
        return None

    all_verified_emails = EmailAddress.objects.filter(
        verified=True, user_id=participant.user_id
    ).values_list("email", flat=True)

    other_verified_emails = set(all_verified_emails) - {participant.email}

    payload = {
        "email": participant.email,
        "affiliation": participant.affiliation,
        "other_verified_emails": sorted(other_verified_emails),
    }
    # Note that this may be a 400!
    return requests.put(
        urljoin(API_BASE, "api-auth/v1/affiliation/"),
        # NOTE: We sign the payload here, even though current implementations just use the body.
        # This does technically mean that anyone with a valid token can use the token to query any data.
        # However, tokens aren't given to end users, only used on the systems which already have the secret.
        headers={"Authorization": gear_bearer_jwt(**payload)},
        json=payload,
        timeout=10,
    )
