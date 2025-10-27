from __future__ import annotations

import enum
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple, assert_never

from allauth.account.models import EmailAddress
from django.db.models import Count, Exists, OuterRef
from django.db.models.functions import Lower
from mitoc_const import affiliations

from ws import models, tasks

if TYPE_CHECKING:
    from collections.abc import Collection, Iterator


logger = logging.getLogger(__name__)


API_BASE = "https://mitoc-gear.mit.edu/"

JsonDict = dict[str, Any]


class TripsInformation(NamedTuple):
    is_leader: bool
    num_trips_attended: int
    num_trips_led: int
    # Email address as given on Participant object
    # (We assume this is their preferred current email)
    email: str
    # If they are a student & have verified an mit.edu email, we report it
    verified_mit_email: str | None


class MembershipInformation(NamedTuple):
    email: str
    # In order to claim MIT student status, you must verify you own an @mit.edu email.
    # We'll only report this for *current* students (since many others will lack).
    mit_email: str | None
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
        # Future optimization -- rather than fetching info about *all* users,
        # try just those who are active MITOC members.
        # If we wanted, we could try to rely on the cached Membership object.
        # (though that's more prone to failure on cache mismatches)
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

    def _mit_emails(member: dict[str, Any]) -> Iterator[str]:
        for email in {member["email"], *member["alternate_emails"]}:
            if email.lower().endswith("@mit.edu"):  # Exclude alum.mit.edu!
                yield email.lower()

    info = [
        MembershipInformation(
            email=member["email"],
            # If they are a current MIT student, assume they own the first mit.edu.
            # To pay dues on the trips site, we *require* they own an MIT email.
            # However, it's possible a desk worker manually added the membership.
            mit_email=(
                next(_mit_emails(member), None)
                if member["affiliation"]
                in {
                    affiliations.MIT_UNDERGRAD.VALUE,
                    affiliations.MIT_GRAD_STUDENT.VALUE,
                }
                else None
            ),
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
    trips_per_participant: dict[int, int] = dict(
        models.SignUp.objects.filter(on_trip=True)
        .values("participant_id")
        .annotate(num_trips=Count("participant_id"))
        .values_list("participant_id", "num_trips")
    )

    # Technically, yes, one could have multiple verified mit.edu addresses.
    # But that's going to be exceptionally rare, and the dict will handle dupes.
    mit_email_for_students: dict[int, str] = dict(
        models.Participant.objects.filter(
            affiliation__in=[
                affiliations.MIT_UNDERGRAD.CODE,
                affiliations.MIT_GRAD_STUDENT.CODE,
            ],
            user__emailaddress__verified=True,
            user__emailaddress__email__iendswith="@mit.edu",
        ).values_list("pk", "user__emailaddress__email")
    )

    additional_stats = (
        models.Participant.objects.all()
        .annotate(
            # Future optimization: *most* participants don't lead trips
            # Querying those separately should avoid the need to do pointless JOINs
            num_trips_led=Count("trips_led", distinct=True),
            is_active_leader=Exists(
                models.LeaderRating.objects.filter(
                    participant=OuterRef("pk"), active=True
                )
            ),
        )
        .values(
            "pk",
            "user_id",
            "email",
            "is_active_leader",
            "num_trips_led",
        )
    )

    return {
        par["user_id"]: TripsInformation(
            email=par["email"],
            verified_mit_email=mit_email_for_students.get(par["pk"]),
            is_leader=par["is_active_leader"],
            num_trips_attended=trips_per_participant.get(par["pk"], 0),
            num_trips_led=par["num_trips_led"],
        )
        for par in additional_stats
    }


def fetch_membership_information(cache_strategy: CacheStrategy) -> MemberStatsResponse:
    """All current active MITOCers, annotated with additional info.

    For each paying MITOCer, we also mark if they:
    - have attended any trips
    - have led any trips
    - have rented gear
    """
    stats = fetch_geardb_stats_for_all_members(cache_strategy)
    return stats.with_trips_information()
