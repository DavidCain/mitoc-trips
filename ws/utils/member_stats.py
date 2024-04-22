from __future__ import annotations

import enum
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple

from allauth.account.models import EmailAddress
from django.db.models import Case, Count, IntegerField, Q, Sum, When
from django.db.models.functions import Lower
from typing_extensions import assert_never

from ws import models, tasks

if TYPE_CHECKING:
    from collections.abc import Collection


logger = logging.getLogger(__name__)


API_BASE = "https://mitoc-gear.mit.edu/"

JsonDict = dict[str, Any]


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


class MemberStatsResponse(NamedTuple):
    retrieved_at: datetime
    members: list[MembershipInformation]

    def with_trips_information(self) -> MemberStatsResponse:
        """Add information about trip attendance to the geardb members."""
        info_by_user_id = _get_trip_stats_by_user()

        # Bridge from a lowercase email address to a Trips user ID
        # Yes, lowercasing an email could technically cause collisions (Turkish dotless i)...
        # This is just for statistics, though, so hopefully it's fine.
        email_to_user_id: dict[str, int] = dict(
            EmailAddress.objects.filter(verified=True)
            .annotate(lower_email=Lower("email"))
            .values_list("lower_email", "user_id")
        )

        def trips_info_for(known_emails: Collection[str]) -> TripsInformation | None:
            all_known_emails = (e.lower() for e in known_emails)

            try:
                # Maintain ordering, to prefer first email!
                email = next(e for e in all_known_emails if e in email_to_user_id)
            except StopIteration:
                return None

            user_id = email_to_user_id[email]

            # Notably, possible to have a user without a participant!
            return info_by_user_id.get(user_id)

        augmented_members: list[MembershipInformation] = []
        for info in self.members:
            trips_info = trips_info_for({info.email, *info.alternate_emails})
            augmented_members.append(
                info._replace(
                    # Email will only be shown in the raw JSON.
                    # Because this is a leaders-only viewpoint, we can show such personal info.
                    # Given that we also count rentals, we *might* consider a BOD-only restriction.
                    email=trips_info.email if trips_info else info.email,
                    trips_information=trips_info,
                )
            )
        return MemberStatsResponse(
            retrieved_at=self.retrieved_at,
            members=augmented_members,
        )


class CacheStrategy(enum.Enum):
    # The default option is fast *and* is resilient against geardb outages.
    # We always report the cache, but refresh asynchronously if needed.
    FETCH_IF_STALE_ASYNC = "default"

    # If the cache is too stale (1 hour, presently) block until we refresh.
    # Carries the risk of 500ing if the cache is stale, but guarantees fresh.
    FETCH_IF_STALE_SYNCHRONOUS = "fetch_if_stale"

    # Always query gear database for the latest
    # Will still write its results to the cache for others to use.
    BYPASS = "bypass"


def fetch_geardb_stats_for_all_members(
    cache_strategy: CacheStrategy,
) -> MemberStatsResponse:
    """Report emails & rental activity for all members with current dues."""

    acceptable_staleness = timedelta(
        hours=(0 if cache_strategy == CacheStrategy.BYPASS else 1)
    ).total_seconds()

    if (
        # assert_never() will not work with `in`!
        cache_strategy == CacheStrategy.BYPASS  # noqa: PLR1714
        or cache_strategy == CacheStrategy.FETCH_IF_STALE_SYNCHRONOUS
    ):
        # Run synchronously, will block the process for up to 5 seconds!
        cached = tasks.update_member_stats(acceptable_staleness)
    elif cache_strategy == CacheStrategy.FETCH_IF_STALE_ASYNC:
        # Take whatever was last cached -- we'll refresh it async if needed.
        cached = models.MembershipStats.load()
        tasks.update_member_stats.delay(acceptable_staleness)
    else:
        assert_never(cache_strategy)

    info = [
        MembershipInformation(
            email=member["email"],
            alternate_emails=member["alternate_emails"],
            person_id=int(member["id"]),
            affiliation=member["affiliation"],
            num_rentals=int(member["num_rentals"]),
            # We don't have any trips information here.
            trips_information=None,
        )
        for member in cached.response
    ]
    return MemberStatsResponse(cached.retrieved_at, info)


def _get_trip_stats_by_user() -> dict[int, TripsInformation]:
    """Give important counts, indexed by user IDs.

    Each participant has a singular underlying user. This user has one or more
    email addresses, which form the link back to the gear database.
    """
    # Notably this counts *all* historical attendance on trips.
    # Do we perhaps just want to count participants who've gone on a trip this last year?
    signup_on_trip = Case(
        When(signup__on_trip=True, then=1), default=0, output_field=IntegerField()
    )

    trips_per_participant: dict[int, int] = dict(
        models.Participant.objects.all()
        .annotate(
            # NOTE: Adding other annotations results in double-counting signups
            # (We do multiple JOINs, and can't easily pass a DISTINCT to the Sum)
            num_trips_attended=Sum(signup_on_trip)
        )
        .values_list("pk", "num_trips_attended")
    )

    additional_stats = models.Participant.objects.all().annotate(
        num_discounts=Count("discounts", distinct=True),
        num_trips_led=Count("trips_led", distinct=True),
        num_leader_ratings=Count("leaderrating", filter=Q(leaderrating__active=True)),
    )

    return {
        par.user_id: TripsInformation(
            email=par.email,
            is_leader=bool(par.num_leader_ratings),
            num_trips_attended=trips_per_participant[par.pk],
            num_trips_led=par.num_trips_led,
            num_discounts=par.num_discounts,
        )
        for par in additional_stats
    }


def fetch_membership_information(cache_strategy: CacheStrategy) -> MemberStatsResponse:
    """All current active members, annotated with additional info.

    For each paying member, we also mark if they:
    - have attended any trips
    - have led any trips
    - have rented gear
    - make use MITOC discounts
    """
    stats = fetch_geardb_stats_for_all_members(cache_strategy)
    return stats.with_trips_information()
