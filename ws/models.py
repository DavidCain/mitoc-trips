import re
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

import markdown2
from allauth.account.models import EmailAddress
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GistIndex
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import format_lazy
from localflavor.us.models import USStateField
from mitoc_const import affiliations
from mitoc_const.membership import RENEWAL_ALLOWED_WITH_DAYS_LEFT
from phonenumber_field.modelfields import PhoneNumberField

import ws.utils.dates as date_utils
from ws import enums
from ws.utils.avatar import avatar_url

alphanum = RegexValidator(
    r'^[a-zA-Z0-9 ]*$', "Only alphanumeric characters and spaces allowed"
)


class NoApplicationDefined(Exception):
    pass


class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):  # pylint: disable=signature-differs
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pylint: disable=signature-differs
        pass

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class Car(models.Model):
    # As long as this module is reloaded once a year, this is fine
    # (First license plates were issued in Mass in 1903)
    year_min, year_max = 1903, date_utils.local_now().year + 2
    # Loosely validate - may wish to use international plates in the future
    license_plate = models.CharField(max_length=31, validators=[alphanum])
    state = USStateField()
    make = models.CharField(max_length=63)
    model = models.CharField(max_length=63)
    year = models.PositiveIntegerField(
        validators=[MaxValueValidator(year_max), MinValueValidator(year_min)]
    )
    color = models.CharField(max_length=63)

    def __str__(self):
        return (
            f"{self.color} {self.year} {self.make} "
            f"{self.model} {self.license_plate} ({self.state})"
        )


class EmergencyContact(models.Model):
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField()
    relationship = models.CharField(max_length=63)
    email = models.EmailField()

    def __str__(self):
        return f"{self.name} ({self.relationship}): {self.cell_phone}"


class EmergencyInfo(models.Model):
    emergency_contact = models.OneToOneField(EmergencyContact, on_delete=models.CASCADE)
    allergies = models.CharField(max_length=255)
    medications = models.CharField(max_length=255)
    medical_history = models.TextField(
        max_length=2000, help_text="Anything your trip leader would want to know about."
    )

    def __str__(self):
        return ' | '.join(
            [
                f"Allergies: {self.allergies}"
                f"Medications: {self.medications}"
                f"History: {self.medical_history}"
                f"Contact: {self.emergency_contact}"
            ]
        )


class LeaderManager(models.Manager):
    def get_queryset(self):
        all_participants = super().get_queryset()
        leaders = all_participants.filter(leaderrating__active=True).distinct()
        return leaders.prefetch_related('leaderrating_set')


class Discount(models.Model):
    """Discount at another company available to MITOC members."""

    administrators = models.ManyToManyField(
        'Participant',
        blank=True,
        help_text="Persons selected to administer this discount",
        related_name='discounts_administered',
    )

    active = models.BooleanField(
        default=True, help_text="Discount is currently open & active"
    )
    name = models.CharField(max_length=255)
    summary = models.CharField(max_length=255)
    terms = models.TextField(max_length=4095)
    url = models.URLField(null=True, blank=True)
    ga_key = models.CharField(
        max_length=63,
        # If blank, then we don't actually report this information to a spreadsheet
        blank=True,
        help_text="key for Google spreadsheet with membership information (shared as read-only with the company)",
    )

    time_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    student_required = models.BooleanField(
        default=False, help_text="Discount provider requires recipients to be students"
    )

    report_school = models.BooleanField(
        default=False, help_text="Report MIT affiliation if participant is a student"
    )
    report_student = models.BooleanField(
        default=False,
        help_text="Report MIT affiliation and student status to discount provider",
    )
    report_leader = models.BooleanField(
        default=False, help_text="Report MITOC leader status to discount provider"
    )
    report_access = models.BooleanField(
        default=False,
        help_text="Report if participant should have leader, student, or admin level access",
    )

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.name


class Membership(models.Model):
    """Cached data about a participant's MITOC membership.

    The gear database is the ultimate authority about a given participant's
    membership. However, since paying dues and signing waivers happens so
    rarely (once a year), we can cache this information locally for faster access.

    `membership_expires` and `waiver_expires` should be regarded as the
    _minimum_ date after which the membership/waiver expire. It's possible that
    the gear database actually has a newer membership/waiver, so if we need to
    authoritatively state expiration date, the gear database should be
    consulted.

    Waivers and membership dues that are completed in the usual way trigger
    updates on this model, but it's possible for desk workers to manually
    update membership accounts, and that does not (currently) automatically
    notify this system.
    """

    # We allow renewing membership in the last 40 days of your membership
    # (If you renew during this period, you get a full year + the remaining days)
    # Remove two days to reduce possibility of an "off by one" error in renewal code
    # (that is, somebody paying their dues, but not getting their remaining time added)
    RENEWAL_WINDOW = timedelta(days=RENEWAL_ALLOWED_WITH_DAYS_LEFT - 2)

    membership_expires = models.DateField(
        null=True,
        blank=True,
        help_text="Last day that annual membership dues are valid",
    )
    waiver_expires = models.DateField(
        null=True,
        blank=True,
        help_text="Day after which liability waiver is no longer valid",
    )
    last_cached = models.DateTimeField(auto_now=True)

    @property
    def membership_active(self) -> bool:
        expires = self.membership_expires
        if expires is None:
            return False
        return expires >= date_utils.local_date()

    @property
    def waiver_active(self) -> bool:
        expires = self.waiver_expires
        if expires is None:
            return False
        return expires >= date_utils.local_date()

    def should_sign_waiver_for(self, trip: 'Trip') -> bool:
        """Return if the waiver will be valid for the day of the trip.

        We consider waivers "expired" 365 days after being signed.
        """
        # WS 2021 "trips" are just lectures, so waivers are not needed.
        # Normally, *all* trips require a waiver, so just make this a temporary hack.
        # No trip in January, 2021 will be in-person and requiring a waiver.
        if date(2021, 1, 1) < trip.trip_date < date(2021, 2, 1):
            return False

        if not self.waiver_expires:
            return True

        # Edge case: trip is extremely distant in the future.
        # Signing a new waiver today won't ensure the waiver is valid by that date.
        # We at least have one waiver signed and as a legal agreement it doesn't really 'expire'
        # Allow participants to sign up today - we'll make sure leaders get new waivers closer
        if (trip.trip_date - date_utils.local_date()) >= timedelta(days=364):
            return False

        # Participants should *always* sign if waiver will be dated by trip start.
        return trip.trip_date > self.waiver_expires

    def date_when_renewal_is_recommended(self, report_past_dates: bool) -> date | None:
        """Return the date on which we recommend the participant renews their membership.

        (That date may have been in the past).

        Dates are assumed to be as observed by Eastern time, but it's not important
        that this be precise.
        """
        if not self.membership_expires:
            return None

        earliest_renewal_date = self.membership_expires - self.RENEWAL_WINDOW

        if earliest_renewal_date < date_utils.local_date() and not report_past_dates:
            return None

        return earliest_renewal_date

    @property
    def in_early_renewal_period(self) -> bool:
        """Return if the member is in their last ~40 days of membership, can renew."""
        if not self.membership_active:
            return False
        renewal_date = self.date_when_renewal_is_recommended(report_past_dates=True)
        if renewal_date is None:
            return False
        return renewal_date <= date_utils.local_date()

    @property
    def expiry_if_paid_today(self) -> date:
        """Return the date which membership would expire, if paid today."""
        if not self.in_early_renewal_period:
            return date_utils.local_date() + timedelta(days=365)

        assert self.membership_expires
        return self.membership_expires + timedelta(days=365)

    def should_renew_for(self, trip) -> bool:
        """Return if membership renewal is required to attend a future trip.

        If a participant's membership will expire on the given date, and it's
        close enough in the future that they can renew, we should not allow
        them to sign up for the trip (since they won't be an active member on
        that day).

        Most MITOC trips are announced just a week or two in advance, very few
        are more than 30 days out.
        """
        if not trip.membership_required:
            return False

        today = date_utils.local_date()

        future = today + self.RENEWAL_WINDOW

        if trip.trip_date > future:
            # Trip is too far in the future to request a renewal now
            return False

        expires = self.membership_expires
        will_be_valid_on_date = expires and expires >= trip.trip_date
        return not will_be_valid_on_date

    def __str__(self):
        return (
            f"{self.participant.name}, "
            f"membership: {self.membership_expires}, "
            f"waiver: {self.waiver_expires}"
        )


class Participant(models.Model):
    """Anyone going on a trip needs WIMP info, and info about their car.

    Even leaders will have a Participant record (see docstring of LeaderRating).
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    objects = models.Manager()
    leaders = LeaderManager()
    name = models.CharField(max_length=255)
    cell_phone = PhoneNumberField(blank=True)  # Hi, Sheep.
    last_updated = models.DateTimeField(auto_now=True)
    # `profile_last_updated` is only set when the _participant_ edits their profile
    profile_last_updated = models.DateTimeField(auto_now_add=True)
    emergency_info = models.OneToOneField(EmergencyInfo, on_delete=models.CASCADE)
    email = models.EmailField(
        unique=True,
        help_text=format_lazy(
            'This will be shared with leaders & other participants. '
            '<a href="{url}">Manage email addresses</a>.',
            url=reverse_lazy('account_email'),
        ),
    )
    gravatar_opt_out = models.BooleanField(
        default=False,
        verbose_name="Opt out of Gravatar",
        help_text="Don't use Gravatar to show an avatar for this account",
    )
    send_membership_reminder = models.BooleanField(
        default=False,
        verbose_name="Send annual reminder to renew membership",
        help_text="MITOC cannot automatically renew memberships, but we can send you an email when it's time to renew.",
    )
    car = models.OneToOneField(Car, null=True, blank=True, on_delete=models.CASCADE)

    membership = models.OneToOneField(
        Membership, null=True, blank=True, on_delete=models.CASCADE
    )

    AFFILIATION_CHOICES: list[tuple[str, str | list[tuple[str, str]]]] = [
        (
            'Undergraduate student',
            [
                (affiliations.MIT_UNDERGRAD.CODE, "MIT undergrad"),
                (affiliations.NON_MIT_UNDERGRAD.CODE, "Non-MIT undergrad"),
            ],
        ),
        (
            'Graduate student',
            [
                (affiliations.MIT_GRAD_STUDENT.CODE, "MIT grad student"),
                (affiliations.NON_MIT_GRAD_STUDENT.CODE, "Non-MIT grad student"),
            ],
        ),
        (
            'MIT',
            [
                (affiliations.MIT_AFFILIATE.CODE, 'MIT affiliate (staff or faculty)'),
                (affiliations.MIT_ALUM.CODE, "MIT alum (former student)"),
            ],
        ),
        (affiliations.NON_AFFILIATE.CODE, 'Non-affiliate'),
    ]
    # We used to not collect level of student + MIT affiliation
    # Any participants with single-digit affiliation codes have dated status
    # Old codes were: S (student), M (MIT affiliate), and N (non-affiliated)
    affiliation = models.CharField(max_length=2, choices=AFFILIATION_CHOICES)
    STUDENT_AFFILIATIONS = frozenset(
        {
            affiliations.MIT_UNDERGRAD.CODE,
            affiliations.NON_MIT_UNDERGRAD.CODE,
            affiliations.MIT_GRAD_STUDENT.CODE,
            affiliations.NON_MIT_GRAD_STUDENT.CODE,
        }
    )

    discounts = models.ManyToManyField(Discount, blank=True)

    @property
    def membership_active(self) -> bool:
        """NOTE: This uses the cache, should only be called on a fresh cache."""
        return bool(self.membership and self.membership.membership_active)

    def should_sign_waiver_for(self, trip: 'Trip') -> bool:
        """NOTE: This uses the cache, should only be called on a fresh cache."""
        if not self.membership:
            return True
        return self.membership.should_sign_waiver_for(trip)

    def should_renew_for(self, trip: 'Trip') -> bool:
        """NOTE: This uses the cache, should only be called on a fresh cache."""
        if not trip.membership_required:
            return False
        if not self.membership:
            return True
        return self.membership.should_renew_for(trip)

    def avatar_url(self, size: int = 100) -> str:
        return avatar_url(self, size)

    @staticmethod
    def affiliation_to_membership_price(affiliation: str) -> int:
        prices = {aff.CODE: aff.ANNUAL_DUES for aff in affiliations.ALL}
        return prices.get(affiliation, affiliations.NON_AFFILIATE.ANNUAL_DUES)

    @property
    def annual_dues(self) -> int:
        return self.affiliation_to_membership_price(self.affiliation)

    @property
    def is_student(self) -> bool:
        return self.affiliation in self.STUDENT_AFFILIATIONS

    @property
    def is_mit_student(self) -> bool:
        return self.affiliation in {
            affiliations.MIT_UNDERGRAD.CODE,
            affiliations.MIT_GRAD_STUDENT.CODE,
        }

    @property
    def problems_with_profile(self) -> Iterator[enums.ProfileProblem]:
        """Yield any serious profile errors needing immediate correction.

        These profile errors should prevent the participant from attending a trip.
        """
        if not self.info_current:
            yield enums.ProfileProblem.STALE_INFO

        if not self.emergency_info.emergency_contact.cell_phone:
            yield enums.ProfileProblem.INVALID_EMERGENCY_CONTACT_PHONE
        if ' ' not in self.name:  # pylint: disable=unsupported-membership-test
            yield enums.ProfileProblem.MISSING_FULL_NAME

        emails = self.user.emailaddress_set  # type: ignore [attr-defined]

        if not emails.filter(email=self.email, verified=True).exists():
            yield enums.ProfileProblem.PRIMARY_EMAIL_NOT_VALIDATED

        if self.affiliation_dated:
            yield enums.ProfileProblem.LEGACY_AFFILIATION

    @property
    def info_current(self) -> bool:
        """Whether the participant has recently updated their information.

        This attribute must be true in order to participate on trips, but we
        do allow some browsing of the site before we collect information.

        By contrast, `affiliation_dated` being false will trigger an immediate
        redirect.
        """
        since_last_update = timezone.now() - self.profile_last_updated
        return since_last_update.days < settings.MUST_UPDATE_AFTER_DAYS

    @property
    def affiliation_dated(self) -> bool:
        """The affiliation we have on file is too general/dated.

        For the purposes of better record-keeping, we really need an updated
        affiliation. Redirect the participant urgently.
        """
        if len(self.affiliation) == 1:  # Old one-letter affiliation
            return True

        force_reset = datetime(2018, 10, 27, 4, 30, tzinfo=ZoneInfo('America/New_York'))
        return self.profile_last_updated < force_reset

    @classmethod
    def from_email(cls, email, join_membership=False):
        addr = EmailAddress.objects.filter(email__iexact=email, verified=True).first()
        return cls.from_user(addr.user, join_membership) if addr else None

    @classmethod
    def from_user(
        cls,
        user: User | AnonymousUser,
        join_membership: bool = False,
    ) -> Optional['Participant']:
        if not user.is_authenticated:
            return None

        one_or_none = cls.objects.filter(user_id=user.id)
        if join_membership:
            one_or_none = one_or_none.select_related('membership')

        try:
            return one_or_none.get()
        except cls.DoesNotExist:
            return None

    def attended_lectures(self, year: int) -> bool:
        return self.lectureattendance_set.filter(year=year).exists()

    def missed_lectures(self, year: int) -> bool:
        """Whether the participant missed WS lectures in the given year."""
        if year < 2016:
            return False  # We lack records for 2014 & 2015; assume present
        if year == date_utils.ws_year() and not date_utils.ws_lectures_complete():
            return False  # Lectures aren't over yet, so nobody "missed" lectures

        return not self.attended_lectures(year)

    def missed_lectures_for(self, trip) -> bool:
        """Should we regard the participant as having missed lectures for this trip.

        This only applies to WS trips - all other trips will return False.

        During the first week of Winter School (where people sign up for trips
        _before_ being marked as having attended lectures), we don't want to consider
        people as having missed lectures.
        """
        # Notably, winter trips outside IAP don't require lecture attendance
        if trip.program_enum != enums.Program.WINTER_SCHOOL:
            return False

        return self.missed_lectures(trip.trip_date.year)

    def _cannot_attend_because_missed_lectures(self, trip) -> bool:
        """Return if the participant's lack of attendance should prevent their attendance.

        This method exists to allow WS leaders to attend trips as a
        participant, even if they've missed lectures this year. So long as
        they've been to a recent year's lectures, we'll allow them to sign up
        as participants (though they will still be rendered as having missed
        the current year's lectures in any UI that surfaces that information).
        """
        if not self.missed_lectures_for(trip):
            return False  # Attended this year

        # For Winter School leaders, we have a carve-out if you've attended lectures recently
        if not self.can_lead(enums.Program.WINTER_SCHOOL):
            # (All other participants must have attended this year's lectures)
            return True

        try:
            last_attendance = self.lectureattendance_set.latest('year')
        except LectureAttendance.DoesNotExist:
            return True  # First-time leaders must have attended lectures!

        # Leaders who have attended any of the last 4 years' lectures may attend trips.
        # e.g. if you attended lectures in 2016, you may attend trips in IAP of 2020, but not 2021
        years_since_last_lecture = date_utils.ws_year() - last_attendance.year
        return years_since_last_lecture > 4

    def reasons_cannot_attend(self, trip):
        """Can this participant attend the trip? (based off cached membership)

        - If there are zero reasons, then the participant may attend the trip.
        - If there are one or more reasons, there may others once those are resolved,
          but we opt not to include others, so that we can focus on the most relevant.

        If membership-related reasons (e.g. expired waiver/membership), it's
        important that the caller refresh the cache and try again.
        `utils.membership.reasons_cannot_attend` provides this functionality.
        """
        # NOT_LOGGED_IN and NO_PROFILE_INFO must be raised by other methods (we have a participant)

        if trip.wimp == self:
            # Being the WIMP for the trip absolutely prevents attendance, other rules don't matter.
            yield enums.TripIneligibilityReason.IS_TRIP_WIMP
            return

        if self._cannot_attend_because_missed_lectures(trip):
            yield enums.TripIneligibilityReason.MISSED_WS_LECTURES
            # If the participant missed lectures, exit early and don't consider membership
            # (we don't want folks to pay money, only to realize they cannot attend)
            return

        if any(self.problems_with_profile):
            yield enums.TripIneligibilityReason.PROFILE_PROBLEM

        if self.should_renew_for(trip):
            if self.membership and self.membership.membership_expires:
                yield enums.TripIneligibilityReason.MEMBERSHIP_NEEDS_RENEWAL
            else:
                yield enums.TripIneligibilityReason.MEMBERSHIP_MISSING

        if self.should_sign_waiver_for(trip):
            if self.membership and self.membership.waiver_expires:
                yield enums.TripIneligibilityReason.WAIVER_NEEDS_RENEWAL
            else:
                yield enums.TripIneligibilityReason.WAIVER_MISSING

    def update_membership(
        self,
        membership_expires: date | None = None,
        waiver_expires: date | None = None,
    ) -> tuple[Membership, bool]:
        """Update our own cached membership with new information."""
        acct, created = Membership.objects.get_or_create(participant=self)
        if membership_expires:
            acct.membership_expires = membership_expires
        if waiver_expires:
            acct.waiver_expires = waiver_expires
        acct.save()
        if created:
            self.membership = acct
            self.save()
        return acct, created

    def ratings(self, must_be_active=True, at_time=None, after_time=None):
        """Return all ratings matching the supplied filters.

        must_be_active: Only format a rating if it's still active
        at_time:        Only return ratings before the given time
                        (useful to get a past, but not necessarily current, rating)
        after_time:     Only return ratings created after this time
        """
        # (We do this in raw Python instead of `filter()` to avoid n+1 queries
        # This method should be called when leaderrating_set was prefetched
        ratings = (
            r for r in self.leaderrating_set.all() if r.active or not must_be_active
        )
        if at_time:
            ratings = (r for r in ratings if r.time_created <= at_time)
        if after_time:
            ratings = (r for r in ratings if r.time_created > after_time)
        return ratings

    def name_with_rating(self, trip):
        """Give the leader's name plus rating at the time of the trip.

        Note: Some leaders from Winter School 2014 or 2015 may not have any
        ratings. In those years, we deleted all Winter School ratings at the
        end of the season (so leaders who did not return the next year lost
        their ratings).

        If no rating is found, simply the name will be given.
        """
        required_activity = trip.program_enum.required_activity()
        if required_activity is None:
            return self.name

        day_before = trip.trip_date - timedelta(days=1)
        rating = self.activity_rating(
            required_activity,
            at_time=date_utils.late_at_night(day_before),
            must_be_active=False,
        )
        return f"{self.name} ({rating})" if rating else self.name

    def activity_rating(self, activity_enum: enums.Activity, **kwargs):
        """Return leader's rating for the given activity (if one exists)."""
        ratings = [
            r for r in self.ratings(**kwargs) if r.activity == activity_enum.value
        ]
        if not ratings:
            return None
        return max(ratings, key=lambda rating: rating.time_created).rating

    @property
    def allowed_programs(self) -> Iterator[enums.Program]:
        """Yield all programs which this participant can currently lead."""
        active_ratings = self.leaderrating_set.filter(active=True)
        rated_activities = active_ratings.values_list('activity', flat=True)
        if not rated_activities:
            # Not a MITOC leader, can't lead anything
            return

        iap_ongoing = date_utils.is_currently_iap()
        for program_enum in enums.Program:
            if program_enum == enums.Program.WINTER_SCHOOL and not iap_ongoing:
                continue  # With or without a WS rating, WS trips should only be made in IAP!

            req_activity = program_enum.required_activity()
            if req_activity is None or req_activity.value in rated_activities:
                yield program_enum

    def can_lead(self, program_enum):
        """Can participant lead trips of the given activity type."""
        if program_enum.is_open():
            return self.is_leader

        activity = program_enum.required_activity().value
        return self.leaderrating_set.filter(activity=activity, active=True).exists()

    @property
    def is_leader(self):
        """Query ratings to determine if this participant is a leader.

        When dealing with Users, it's faster to use utils.perms.is_leader
        """
        return self.leaderrating_set.filter(active=True).exists()

    @property
    def email_addr(self):
        return f'"{self.name}" <{self.email}>'

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.name

    class Meta:
        ordering = ['name', 'email']


class MembershipReminder(models.Model):
    """A log of membership reminders that were sent.

    We don't generally log much of anything (by design),
    but this table logs reminder emails that were sent
    (to prevent accidentally reminding the same person twice).
    """

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    reminder_sent_at = models.DateTimeField(
        verbose_name="Last time an email was sent reminding this participant to renew",
        # We allow (temporary) null rows participant to ensure we can lock something
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        if self.reminder_sent_at is None:
            return f'{self.participant}, not yet reminder'

        timestamp = self.reminder_sent_at.isoformat(timespec="minutes")
        return f'{self.participant}, last reminded at {timestamp}'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name='%(app_label)s_%(class)s_par_reminder_sent_at_uniq',
                fields=('participant',),
                condition=Q(reminder_sent_at__isnull=True),
            )
        ]


class PasswordQuality(models.Model):
    """For a given user, information about their password strength.

    This class exists to help us migrate users with known bad passwords
    (checked with the HIBP API) over to more secure options.
    """

    participant = models.OneToOneField(Participant, on_delete=models.CASCADE)
    is_insecure = models.BooleanField(
        default=False, verbose_name="Password shown to be insecure"
    )
    last_checked = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Last time password was checked against HaveIBeenPwned's database",
    )

    def __str__(self):  # pylint: disable=invalid-str-returned
        label = 'INSECURE' if self.is_insecure else 'not known to be breached'
        return f"{label} (as of {self.last_checked})"


class LectureAttendance(models.Model):
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(2016)],
        default=date_utils.ws_year,
        help_text="Winter School year when lectures were attended.",
    )
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    creator = models.ForeignKey(
        Participant, related_name='lecture_attendances_marked', on_delete=models.CASCADE
    )
    time_created = models.DateTimeField(auto_now_add=True)


class WinterSchoolSettings(SingletonModel):
    """Stores settings for the current Winter School.

    These settings should only be modified by the WS chair.
    """

    time_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        Participant, null=True, blank=True, on_delete=models.CASCADE
    )
    allow_setting_attendance = models.BooleanField(
        default=False, verbose_name="Let participants set lecture attendance"
    )
    accept_applications = models.BooleanField(
        default=True, verbose_name="Accept new Winter School leader applications"
    )


class MentorActivity(models.Model):
    """An activity which can be mentored.

    NOTE: This is _not_ the same as activities for which we have activity
    chairs (and which one might receive a leader rating). These activities
    exist as constants on the BaseRating class.
    """

    name = models.CharField(max_length=31, unique=True)

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.name


class BaseRating(models.Model):
    # Activities where you must be rated in order to create/lead a trip
    BIKING = enums.Activity.BIKING.value
    BOATING = enums.Activity.BOATING.value
    CABIN = enums.Activity.CABIN.value
    CLIMBING = enums.Activity.CLIMBING.value
    HIKING = enums.Activity.HIKING.value
    WINTER_SCHOOL = enums.Activity.WINTER_SCHOOL.value
    CLOSED_ACTIVITY_CHOICES = [
        (BIKING, 'Biking'),
        (BOATING, 'Boating'),
        (CABIN, 'Cabin'),
        (CLIMBING, 'Climbing'),
        (HIKING, 'Hiking'),
        (WINTER_SCHOOL, 'Winter School'),
    ]
    CLOSED_ACTIVITIES = [val for (val, label) in CLOSED_ACTIVITY_CHOICES]

    # Activities for which a specific leader rating is not necessary
    # (You must be a MITOC leader, but not necessarily in these activities)
    CIRCUS = 'circus'
    OFFICIAL_EVENT = 'official_event'  # Training, films, etc.
    COURSE = 'course'
    OPEN_ACTIVITY_CHOICES = [
        (CIRCUS, 'Circus'),
        (OFFICIAL_EVENT, 'Official Event'),
        (COURSE, 'Course'),
    ]

    OPEN_ACTIVITIES = [val for (val, label) in OPEN_ACTIVITY_CHOICES]

    ACTIVITIES = CLOSED_ACTIVITIES + OPEN_ACTIVITIES
    ACTIVITY_CHOICES = CLOSED_ACTIVITY_CHOICES + OPEN_ACTIVITY_CHOICES

    time_created = models.DateTimeField(auto_now_add=True)
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    activity = models.CharField(max_length=31, choices=ACTIVITY_CHOICES)
    rating = models.CharField(max_length=31)
    notes = models.TextField(max_length=500, blank=True)  # Contingencies, etc.

    @property
    def activity_enum(self) -> enums.Activity:
        return enums.Activity(self.activity)

    def __str__(self):
        return f"{self.participant.name} ({self.rating}, {self.activity})"

    class Meta:
        abstract = True
        ordering = ["participant"]


class LeaderRating(BaseRating):
    """A leader is just a participant with ratings for at least one activity type.

    The same personal + emergency information is required of leaders, but
    additional fields are present. So, we keep a Participant record for any
    leader. This makes it easy to check if any participant is a leader (just
    see `participant.ratings`) and easy to promote somebody to leader.

    It also allows leaders to function as participants (e.g. if a "SC" leader
    wants to go ice climbing).
    """

    creator = models.ForeignKey(
        Participant, related_name='ratings_created', on_delete=models.CASCADE
    )
    active = models.BooleanField(default=True)


class LeaderRecommendation(BaseRating):
    creator = models.ForeignKey(
        Participant, related_name='recommendations_created', on_delete=models.CASCADE
    )


class BaseSignUp(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    trip = models.ForeignKey("Trip", on_delete=models.CASCADE)
    time_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, max_length=1000)  # e.g. Answers to questions

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.participant.name} on {self.trip}"


class LeaderSignUp(BaseSignUp):
    """Represents a leader who has signed up to join a trip."""

    class Meta:
        ordering = ["time_created"]
        unique_together = ('participant', 'trip')


class SignUp(BaseSignUp):
    """An editable record relating a Participant to a Trip.

    The time of creation determines ordering in first-come, first-serve.
    """

    order = models.IntegerField(null=True, blank=True)  # As ranked by participant
    manual_order = models.IntegerField(null=True, blank=True)  # Order on trip

    on_trip = models.BooleanField(default=False)

    # pylint: disable=arguments-differ
    def save(self, **kwargs):
        """Assert that the Participant is not signing up twice.

        The AssertionError here should never be thrown - it's a last defense
        against a less-than-obvious implementation of adding Participant
        records after getting a bound form.
        """
        if not kwargs.pop('commit', True):
            assert self.trip not in self.participant.trip_set.all()
        super().save(**kwargs)

    class Meta:
        # When ordering for an individual, should order by priority (i.e. 'order')
        # When ordering for a specific trip, should order by:
        # 1. `manual_order` (applied if leaders sort signups)
        # 2. `last_updated` (first to be on the trip -> first on trip)
        ordering = ["manual_order", "last_updated"]
        unique_together = ('participant', 'trip')


class TripInfo(models.Model):
    last_updated = models.DateTimeField(auto_now=True)

    drivers = models.ManyToManyField(
        Participant,
        blank=True,
        help_text=format_lazy(
            'If a trip participant is driving, but is not on this list, '
            'they must first submit <a href="{url}#car">information about their car</a>. '
            'They should then be added here.',
            url=reverse_lazy('edit_profile'),
        ),
    )
    start_location = models.CharField(max_length=127)
    start_time = models.CharField(max_length=63)
    turnaround_time = models.CharField(
        max_length=63,
        blank=True,
        help_text="The time at which you'll turn back and head for your car/starting location",
    )
    return_time = models.CharField(
        max_length=63,
        help_text="When you expect to return to your car/starting location "
        "and be able to call the WIMP",
    )
    worry_time = models.CharField(
        max_length=63,
        help_text="Suggested: 7 pm, or return time +2 hours (whichever is later). "
        "If the WIMP has not heard from you after this time and is unable "
        "to make contact with any leaders or participants, "
        "the authorities will be called.",
    )
    itinerary = models.TextField(
        help_text="A detailed account of your trip plan. "
        "Where will you be going? What route will you be taking? "
        "Include trails, peaks, intermediate destinations, back-up plans- "
        "anything that would help rescuers find you."
    )


trips_search_vector = (
    SearchVector('name', config='english', weight='A')
    + SearchVector('description', config='english', weight='B')
    + SearchVector('prereqs', config='english', weight='B')
    + SearchVector('activity', 'trip_type', config='english', weight='C')
)


class Trip(models.Model):
    # When ordering trips which need approval, apply consistent ordering
    # (Defined here to keep the table's default ordering in sync with prev/next buttons
    ordering_for_approval: tuple[str, ...] = (
        'trip_date',
        'trip_type',
        'info',
        'winter_terrain_level',
    )

    last_updated_by = models.ForeignKey(
        Participant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="trips_updated",
    )
    edit_revision = models.PositiveIntegerField(
        default=0,
        help_text="An incremented integer, to avoid simultaneous edits to the trip.",
    )
    program = models.CharField(
        max_length=255,
        choices=enums.Program.choices(),
        # For now, just default program to 'none' (we don't yet have form handling)
        # Later, do not define a default - we'll populate based on leader/time of year
        default=enums.Program.NONE.value,
        db_index=True,
    )
    activity = models.CharField(
        max_length=31,
        choices=LeaderRating.ACTIVITY_CHOICES,
        default=LeaderRating.WINTER_SCHOOL,
    )
    trip_type = models.CharField(
        max_length=255,
        verbose_name='Primary trip activity',
        choices=enums.TripType.choices(),
        db_index=True,
    )
    creator = models.ForeignKey(
        Participant, related_name='created_trips', on_delete=models.CASCADE
    )
    # Leaders should be privileged at time of trip creation, but may no longer
    # be leaders later (and we don't want to break the relation)
    leaders = models.ManyToManyField(Participant, related_name='trips_led', blank=True)
    wimp = models.ForeignKey(
        Participant,
        null=True,
        blank=True,
        related_name='wimp_trips',
        verbose_name='WIMP',
        on_delete=models.CASCADE,
        help_text="Ensures the trip returns safely. "
        "Can view trip itinerary, participant medical info.",
    )
    name = models.CharField(max_length=127)
    description = models.TextField(
        help_text=mark_safe(  # noqa: S308
            '<a href="https://github.com/adam-p/markdown-here/wiki/Markdown-Cheatsheet">'
            "Markdown</a> supported! "
            'Please use HTTPS images sparingly, and only if properly licensed.'
        )
    )
    summary = models.CharField(
        help_text="Brief summary of the trip, to be displayed on lists of all trips",
        max_length=80,
    )
    maximum_participants = models.PositiveIntegerField(
        default=8, verbose_name="Max participants"
    )
    difficulty_rating = models.CharField(max_length=63)
    level = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="This trip's A, B, or C designation (plus I/S rating if applicable).",
    )
    winter_terrain_level = models.CharField(
        verbose_name='Terrain level',
        null=True,
        blank=True,
        max_length=1,
        choices=[
            ('A', 'A: <1 hour to intensive care, below treeline'),
            ('B', 'B: >1 hour to intensive care, below treeline'),
            ('C', 'C: above treeline'),
        ],
        help_text=mark_safe(  # noqa: S308
            'Trip leaders must meet <a href="/help/participants/ws_ratings/">requirements for terrain & activity ratings</a>.',
        ),
        db_index=True,
    )
    prereqs = models.CharField(max_length=255, blank=True, verbose_name="Prerequisites")
    chair_approved = models.BooleanField(default=False)
    notes = models.TextField(
        blank=True,
        max_length=2000,
        help_text="Participants must add notes to their signups if you complete this field. "
        "This is a great place to ask important questions.",
    )

    time_created = models.DateTimeField(auto_now_add=True)
    last_edited = models.DateTimeField(auto_now=True)
    trip_date = models.DateField(default=date_utils.nearest_sat, db_index=True)
    signups_open_at = models.DateTimeField(
        # Rounding to whole minutes simplifies UX on trip creation form
        # (seconds field will be hidden by most browsers, see `step` attribute too!)
        default=date_utils.local_now_to_the_minute,
    )
    signups_close_at = models.DateTimeField(
        default=date_utils.default_signups_close_at, null=True, blank=True
    )

    # Boolean settings
    # ----------------
    membership_required = models.BooleanField(
        default=True,
        help_text="Require an active MITOC membership to participate (waivers are always required).",
    )
    allow_leader_signups = models.BooleanField(
        default=False,
        help_text="Leaders can add themselves directly to the list of trip leaders, even if trip is full or in lottery mode. "
        "Recommended for Circuses!",
    )
    honor_participant_pairing = models.BooleanField(
        default=True,
        help_text="Try to place paired participants together on the trip (if both sign up).",
    )
    let_participants_drop = models.BooleanField(
        default=False,
        help_text="Allow participants to remove themselves "
        "from the trip any time before its start date.",
    )
    requires_reimbursement = models.BooleanField(
        default=False,
        help_text="If you have an approved budget for this trip, you must register with Atlas.",
    )

    info = models.OneToOneField(
        TripInfo, null=True, blank=True, on_delete=models.CASCADE
    )

    signed_up_participants = models.ManyToManyField(Participant, through=SignUp)
    algorithm = models.CharField(
        max_length=31,
        default='lottery',
        choices=[('lottery', 'lottery'), ('fcfs', 'first-come, first-serve')],
    )

    lottery_task_id = models.CharField(
        max_length=36, unique=True, null=True, blank=True
    )
    lottery_log = models.TextField(null=True, blank=True)

    def __str__(self):  # pylint: disable=invalid-str-returned
        return self.name

    def description_to_text(self, maxchars: int | None = None) -> str:
        html = markdown2.markdown(self.description)
        text = BeautifulSoup(html, 'html.parser').text.strip()
        text = re.sub(r'[\s\n\r]+', ' ', text)  # (make sure newlines are single spaces)
        if maxchars is None or maxchars > len(text):
            return text
        cutoff = max(maxchars - 3, 0)
        return text[:cutoff].strip() + '...'

    @property
    def program_enum(self):
        """Convert the string constant value to an instance of the enum."""
        return enums.Program(self.program)

    def winter_rules_apply(self):
        return self.program_enum.winter_rules_apply()

    # TODO: activity is deprecated. Remove this once `trip.activity` purged.
    def get_legacy_activity(self):
        """Return an 'activity' from the given program."""
        activity_enum = self.program_enum.required_activity()
        return activity_enum.value if activity_enum else 'official_event'

    def required_activity_enum(self):
        return self.program_enum.required_activity()

    @property
    def trip_type_enum(self):
        """Convert the string constant value to an instance of the enum."""
        return enums.TripType(self.trip_type)

    @property
    def feedback_window_passed(self):
        return self.trip_date < (date_utils.local_date() - timedelta(30))

    @property
    def on_trip_or_waitlisted(self):
        """All signups for participants either on the trip or waitlisted."""
        on_trip_or_waitlisted = Q(on_trip=True) | Q(waitlistsignup__isnull=False)
        return self.signup_set.filter(on_trip_or_waitlisted)

    @property
    def _within_three_days(self):
        """Return a date range for use with Django's `range` function."""
        return (self.trip_date - timedelta(days=3), self.trip_date + timedelta(days=3))

    def _other_signups(self, par_pks):
        """Return participant signups for trips happening around this time.

        Specifically, for each given participant, find all other trips that
        they're on in a three day window around this trip.
        """
        return (
            SignUp.objects.filter(on_trip=True, participant_id__in=par_pks)
            .exclude(trip=self)
            .filter(trip__trip_date__range=self._within_three_days)
            # Manual hack for weekend 3 of WS: don't count lectures or shuttles
            .exclude(trip_id__in=[1506, 1476, 1477])
            .select_related('trip')
            .order_by('trip__trip_date')
        )

    def other_trips_by_participant(
        self,
        for_participants: Iterable[Participant] | None = None,
    ) -> Iterator[tuple[int, list['Trip']]]:
        """Identify which other trips this trip's participants are on.

        Specifically, for each participant that is signed up for this trip,
        find all other trips that they're either leading or participating in
        within a three-day window. By default, this includes participants who
        are waitlisted as well: knowing about the other trips a participant is
        attending can be helpful when considering moving them onto the trip.

        This method helps trip leaders coordinate driving, cabin stays, and the
        transfer of gear between trips.
        """
        if for_participants:
            par_pks = [participant.pk for participant in for_participants]
        else:
            par_pks = [s.participant_id for s in self.on_trip_or_waitlisted]
        trips_by_par: dict[int, list[Trip]] = {pk: [] for pk in par_pks}

        # Start by identifying trips the participants are attending as participants
        for signup in self._other_signups(par_pks):
            trips_by_par[signup.participant_id].append(signup.trip)

        # Some participants may also be leading other trips. Include those!
        trips_led_by_participants = (
            type(self)
            .objects.filter(
                leaders__in=par_pks, trip_date__range=self._within_three_days
            )
            .order_by('trip_date')
            .annotate(leader_pk=F('leaders'))
        )
        for trip in trips_led_by_participants.order_by('-trip_date', '-time_created'):
            trips_by_par[trip.leader_pk].append(trip)
            del trip.leader_pk  # Remove annotation so it's not accessed elsewhere

        # Combine trips where participants are leading & participating
        for par_pk in par_pks:
            trips = trips_by_par[par_pk]
            yield par_pk, sorted(trips, key=lambda t: t.trip_date)

    @property
    def single_trip_pairing(self):
        """Return if the trip will apply pairing as a single lottery trip."""
        if self.algorithm != "lottery":
            return False  # Trip is FCFS, or lottery has completed
        if self.program_enum == enums.Program.WINTER_SCHOOL:
            return False  # Winter School trips do their own lottery
        return self.honor_participant_pairing

    @property
    def in_past(self):
        return self.trip_date < date_utils.local_date()

    @property
    def less_than_a_week_away(self) -> bool:
        """Return if the trip is taking place less than a week away.

        If true, this means we can refer to the trip's date unambiguously by
        just day of the week.
        """
        if not self.upcoming:  # Don't count today or past trips
            return False
        time_diff = self.trip_date - date_utils.local_date()
        return time_diff.days < 7

    @property
    def upcoming(self):
        return self.trip_date > date_utils.local_date()

    @property
    def _is_winter_school_trip_between_lotteries(self):
        """Return if this WS trip is between lotteries.

        This exists to solve a specific edge case - a WS trip that's created
        on, say, a Friday night to take place the immediate Saturday
        afterwards. It doesn't make sense for this trip to be a lottery trip,
        since it'll be over by the time the next lottery runs.
        """
        if self.program_enum != enums.Program.WINTER_SCHOOL:
            return False

        next_lottery = date_utils.next_lottery()
        past_lottery = date_utils.lottery_time(next_lottery - timedelta(days=7))

        return (
            date_utils.local_now() > past_lottery
            and self.midnight_before < next_lottery
        )

    @property
    def midnight_before(self):
        day_before = self.trip_date - timedelta(days=1)
        return date_utils.late_at_night(day_before)

    @property
    def fcfs_close_time(self):
        return date_utils.fcfs_close_time(self.trip_date)

    @property
    def open_slots(self):
        accepted_signups = self.signup_set.filter(on_trip=True)
        return self.maximum_participants - accepted_signups.count()

    @property
    def signups_open(self):
        """If signups are currently open."""
        return self.signups_opened and not self.signups_closed

    @property
    def signups_opened(self):
        """If signups opened at some time in the past.

        They may have since closed!
        """
        return timezone.now() > self.signups_open_at

    @property
    def signups_closed(self):
        """If a close time is given, return if that time is passed."""
        return self.signups_close_at and timezone.now() > self.signups_close_at

    @property
    def signups_not_yet_open(self):
        """True if signups open at some point in the future, else False."""
        return timezone.now() < self.signups_open_at

    @property
    def last_of_priority(self):
        """The 'manual_order' value for a signup to be priority, but below others.

        That is, leader-ordered signups should go above other signups. (Let's
        say that a leader is organizing signups, but new signups come in before
        they submit the ordering - we want to be sure all their ordering goes
        above any new signups).
        """
        last_signup = self.signup_set.last()
        if last_signup is None:
            return 1
        return (last_signup.manual_order or 0) + 1

    @property
    def info_editable(self):
        now = date_utils.local_now()

        # Past trips may not be edited!
        if now.date() > self.trip_date:
            return False

        # Otherwise, info (including itinerary) should be editable after the cutoff has passed
        return now > date_utils.itinerary_available_at(self.trip_date)

    def make_fcfs(self, signups_open_at=None):
        """Set the algorithm to FCFS, adjust signup times appropriately."""
        self.algorithm = 'fcfs'
        now = date_utils.local_now()
        if signups_open_at:
            self.signups_open_at = signups_open_at
        elif date_utils.wed_morning() <= now < date_utils.closest_wed_at_noon():
            # If posted between lottery time and noon, make it open at noon
            self.signups_open_at = date_utils.closest_wed_at_noon()
        else:
            self.signups_open_at = now

        # If a Winter School trip is last-minute, occurring mid-week,
        # we end up with a close time in the past (preventing trip creation)
        if self.fcfs_close_time > now:
            self.signups_close_at = self.fcfs_close_time

    def clean(self):
        """Ensure that all trip dates are reasonable."""
        if not self.time_created:  # Trip first being created
            if self.signups_closed:
                raise ValidationError("Signups can't be closed already!")
            # Careful here - don't want to disallow editing of past trips
            if self.trip_date < date_utils.local_date():
                raise ValidationError("Trips can't occur in the past!")

            if self._is_winter_school_trip_between_lotteries:
                self.make_fcfs()

        close_time = self.signups_close_at
        if close_time and close_time < self.signups_open_at:
            raise ValidationError("Trips cannot open after they close.")

    def leaders_with_rating(self):
        """All leaders with the rating they had at the time of the trip."""
        return [leader.name_with_rating(self) for leader in self.leaders.all()]

    @classmethod
    def search_trips(cls, text: str, filters: None | Q, limit: int = 100):
        trips = cls.objects.filter(filters) if filters else cls.objects.all()
        # It's valid to not provide a search term at all.
        # In this case, there's no real meaningful way to "rank" matches; put newest first.
        if not text:
            return trips.order_by('-pk')[:limit]

        query = SearchQuery(text)
        return (
            trips.annotate(
                search=trips_search_vector,
                rank=SearchRank(trips_search_vector, query),
            )
            .filter(search=text)
            .order_by('-rank')[:limit]
        )

    @property
    def prefilled_atlas_form_link(self) -> str:
        """Pre-fill known information for submission on the Atlas form link."""
        leaders = list(self.leaders.order_by('name'))
        trip_link = reverse('view_trip', args=(self.pk,))
        prefilled_values = {
            'usp': 'pp_url',
            'entry.64030440': self.name,
            'entry.14051799': ', '.join(leader.name for leader in leaders),
            'entry.1718831235': ', '.join(leader.email for leader in leaders),
            'entry.801739390': urljoin('https://mitoc-trips.mit.edu', trip_link),
            'entry.260268802': self.summary,
            'entry.1651767815': self.trip_date.isoformat(),
            # 'entry.240172613':Food
            # 'entry.2093739261':10
        }
        try:
            info: TripInfo | None = self.info
        except TripInfo.DoesNotExist:
            info = None

        if info:
            prefilled_values.update(
                {
                    'entry.1852696041': info.start_location,
                    # We record start time, but only as free text...
                    # 'entry.845875220': '10:00',
                    # We don't record trip end date!
                    # 'entry.2038085654':2022-12-30
                    # We record end time, but only as free text...
                    # 'entry.2004693073':23:45
                }
            )

        return (
            'https://docs.google.com/forms/d/e/1FAIpQLSeBgwQXEzbuBVdEpS6hAaII-sdlEajVnMQC84igt8plmigRdw/viewform?'
            + urlencode(prefilled_values)
        )

    class Meta:
        ordering = ["-trip_date", "-time_created"]
        indexes = [
            GistIndex(
                trips_search_vector,
                name='search_vector_idx',
            )
        ]


class BygonesManager(models.Manager):
    """Automatically exclude feedback that's sufficiently far in the past."""

    def get_queryset(self):
        feedback = super().get_queryset()
        now = date_utils.local_now()

        bygones_window = timedelta(days=13 * 30)
        # Only for WS 2022: we temporarily show feedback for 25 months
        if date(2021, 12, 19) < now.date() < date(2022, 2, 1):
            # TEMPORARY: Use a ~25 month window until the end of WS 2022
            # (we can clean this up later)
            bygones_window = timedelta(days=25 * 30)

        feedback_cutoff = now - bygones_window
        return feedback.exclude(trip__trip_date__lt=feedback_cutoff)


class Feedback(models.Model):
    """Feedback given for a participant on one trip."""

    objects = BygonesManager()  # By default, ignore feedback older than ~13 months
    everything = models.Manager()  # But give the option to look at older feedback

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    leader = models.ForeignKey(
        Participant, related_name="authored_feedback", on_delete=models.CASCADE
    )
    showed_up = models.BooleanField(default=True)
    comments = models.TextField(max_length=2000)
    # Allows general feedback (i.e. not linked to a trip)
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.CASCADE)
    time_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.participant}: "{self.comments}" - {self.leader}'

    class Meta:
        ordering = ["participant", "-time_created"]


class LotteryInfo(models.Model):
    """Persists from week-to-week, but can be changed."""

    participant = models.OneToOneField(Participant, on_delete=models.CASCADE)
    car_status = models.CharField(
        max_length=7,
        choices=[
            ("none", "Not driving"),
            ("own", "Can drive others"),
            ("rent", "Willing to rent"),
            ("self", "Can drive self"),
        ],
        default="none",
    )
    number_of_passengers = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(13, message="Do you drive a bus?")],
    )
    last_updated = models.DateTimeField(auto_now=True)
    paired_with = models.ForeignKey(
        Participant,
        null=True,
        blank=True,
        related_name='paired_by',
        on_delete=models.CASCADE,
    )

    @property
    def reciprocally_paired_with(self):
        """Return requested partner if they also requested to be paired."""
        if not (self.pk and self.paired_with):  # Must be saved & paired!
            return None

        try:
            other_paired_id = self.paired_with.lotteryinfo.paired_with_id
        except self.DoesNotExist:  # Paired participant has no lottery info
            return None

        if not other_paired_id:
            return None

        reciprocal = other_paired_id == self.participant_id
        return self.paired_with if reciprocal else None

    @property
    def is_driver(self):
        return self.car_status in ['own', 'rent']

    class Meta:
        ordering = ["car_status", "number_of_passengers"]


class LotterySeparation(models.Model):
    """When running the Winter School lottery, ensure that two participants are separate.

    This can be thought of as the opposite of LotteryInfo.paired_with

    Whoever initiates this separation is expressing an intent to not be placed
    on trips with the blocked participant. The blocked participant likely does
    not know this request has been made (nor have they necessarily done anything
    wrong). Accordingly, the blocked participant will not suffer any negative
    consequences in the lottery.
    """

    time_created = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(
        Participant, related_name='separations_created', on_delete=models.CASCADE
    )

    initiator = models.ForeignKey(
        Participant,
        help_text="Participant requesting a separation",
        related_name='separations_initiated',
        on_delete=models.CASCADE,
    )

    recipient = models.ForeignKey(
        Participant,
        help_text="The participant with whom the initiator should not be placed on a trip",
        related_name='separations_received',
        on_delete=models.CASCADE,
    )

    class Meta:
        # TODO (Django 2.2+): Add constraint that initiator != recipient
        unique_together = ('initiator', 'recipient')


class LotteryAdjustment(models.Model):
    """A manual adjustment that can be made to the lottery.

    In some exceptional circumstances, a participant may have an extremely
    unsavory outcome in the lottery. For instance, a driver may drop off a
    trip, causing another participant to be forced off. There may not be enough
    gear for the participant to safely attend a trip. Whatever the reason,
    objects in this class provide a mechanism of righting those wrongs by
    granting the participants a boost in the next lottery run.

    It's expected that each participant have no more than one adjustment in place
    at any given time.
    """

    time_created = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(
        help_text="Time at which this override should no longer apply"
    )
    creator = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name='adjustments_made'
    )
    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name='adjustments_received'
    )

    # Lower value: Ranked earlier in the lottery
    # Higher value: Ranked later in the lottery
    adjustment = models.IntegerField()

    def __str__(self):
        effect = "boost" if self.adjustment < 0 else "hinder"
        expires = datetime.strftime(self.expires, "%Y-%m-%d %H:%M")
        return f"{effect} {self.participant.name} ({self.adjustment}) until {expires}"


class WaitListSignup(models.Model):
    """Intermediary between initial signup and the trip's waiting list."""

    signup = models.OneToOneField(SignUp, on_delete=models.CASCADE)
    waitlist = models.ForeignKey("WaitList", on_delete=models.CASCADE)
    time_created = models.DateTimeField(auto_now_add=True)
    # Specify to override ordering by time created
    # TODO: Make this *ascending* (so 1 is first, 2 is second)
    # Right now, it's descending - which is both confusing & conflicts with SignUp
    manual_order = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.signup.participant.name} waitlisted on {self.signup.trip}"

    class Meta:
        # TODO (Django 2): Use F-expressions. [F('manual_order').desc(nulls_last=True), ...]
        # TODO (Django 2): Also update WaitList.signups property definition
        # WARNING: Postgres will put nulls first, not last.
        ordering = ["-manual_order", "time_created", "pk"]  # NOT CORRECT!
        # WARNING: This default ordering is not fully correct. Manually call `order_by`)


class WaitList(models.Model):
    """Treat the waiting list as a simple FIFO queue."""

    trip = models.OneToOneField(Trip, on_delete=models.CASCADE)
    unordered_signups = models.ManyToManyField(SignUp, through=WaitListSignup)

    @property
    def signups(self):
        """Return signups ordered with the waitlist rules.

        This method is useful because the SignUp object has the useful information
        for display, but the WaitListSignup object has information for ordering.
        """
        # TODO (Django 2): Just use the below, once we can use F-expressions in `ordering`
        # return self.unordered_signups.order_by('waitlistsignup')
        return self.unordered_signups.order_by(
            F('waitlistsignup__manual_order').desc(nulls_last=True),
            F('waitlistsignup__time_created').asc(),
        )

    @property
    def first_of_priority(self):
        """The 'manual_order' value to be first in the waitlist."""
        # TODO (Django 2): Just use the below, refactor code to avoid extra lookups
        # first_wl_signup = self.waitlistsignup_set.first()
        first_signup = self.signups.first()
        if first_signup is None:
            return 10
        return (first_signup.waitlistsignup.manual_order or 0) + 1

    @property
    def last_of_priority(self):
        """The 'manual_order' value to be below all manual orders, but above non-ordered.

        Waitlist signups are ordered first by `manual_order`, then by time created. This
        method is useful for the scenario when you want to give somebody priority in the
        waitlist, but to not surpass others who were previously added to the top of the
        waitlist.
        """
        # TODO (Django 2): Just use the below
        # last_wl_signup = self.waitlistsignup_set.filter(manual_order__isnull=False).last()
        last_wl_signup = (
            self.waitlistsignup_set.filter(manual_order__isnull=False)
            .order_by(F('manual_order').desc(nulls_last=True))
            .last()
        )

        # Larger number == sooner or list
        if last_wl_signup is None or last_wl_signup.manual_order is None:
            return 10
        return last_wl_signup.manual_order - 1


class LeaderApplication(models.Model):
    """Abstract parent class for all leader applications (doubles as a factory)

    To create a new leader application, write the class:

       <Activity>LeaderApplication (naming matters, see code comments)
    """

    participant = models.ForeignKey(Participant, on_delete=models.CASCADE)
    time_created = models.DateTimeField(auto_now_add=True)
    previous_rating = models.CharField(
        max_length=255, blank=True, help_text="Previous rating (if any)"
    )
    archived = models.BooleanField(
        default=False,
        help_text="Application should not be considered pending. Allows participant to submit another application if they desire.",
    )
    # desired_rating = ... (a CharField, but can vary per application)
    year = models.PositiveIntegerField(
        validators=[MinValueValidator(2014)],
        # TODO: Don't define a `default` at all, just let forms populate it.
        default=date_utils.ws_year,
        help_text="Year this application pertains to.",
    )

    @property
    def rating_given(self):
        """Return any activity rating created after this application."""
        return self.participant.activity_rating(
            enums.Activity(self.activity),
            must_be_active=True,
            after_time=self.time_created,
        )

    @classmethod
    def application_year_for_activity(cls, activity: enums.Activity) -> int:
        if activity == enums.Activity.WINTER_SCHOOL:
            return date_utils.ws_year()
        return date_utils.local_date().year

    @classmethod
    def accepting_applications(cls, activity: enums.Activity) -> bool:
        application_defined = cls.can_apply_for_activity(activity)

        # The climbing activity is accepting applications, but through a form.
        # We want to make sure that we still regard applications as being accepted.
        # (In the future, we might delete the `ClimbingLeaderApplication` model entirely
        if activity == enums.Activity.CLIMBING:
            return True

        if activity != enums.Activity.WINTER_SCHOOL:
            # For non-WS activity types, it's sufficient to just have a form defined.
            # (These activities do not support turning on & off the ability to apply)
            return application_defined

        # WinterSchoolLeaderApplication is clearly defined.
        assert application_defined, "Winter School application not defined!"

        ws_settings = WinterSchoolSettings.load()
        return ws_settings.accept_applications

    @staticmethod
    def can_apply_for_activity(activity: enums.Activity) -> bool:
        """Return if an application exists for the activity."""
        try:
            LeaderApplication.model_from_activity(activity)
        except NoApplicationDefined:
            return False
        return True

    @classmethod
    def can_reapply(cls, latest_application):
        """Return if a participant can re-apply to the activity, given their latest application.

        This implements the default behavior for most activities.
        Other application types may subclass to implement their own behavior!
        """
        # Allow upgrades after 2 weeks, repeat applications after ~6 months
        waiting_period_days = 14 if latest_application.rating_given else 180
        time_passed = date_utils.local_now() - latest_application.time_created
        return time_passed > timedelta(days=waiting_period_days)

    @property
    def activity(self) -> str:
        """Extract the activity name from the class name/db_name.

        Meant to be used by inheriting classes, for example:
            WinterSchoolLeaderApplication -> 'winter_school'
            ClimbingLeaderApplication -> 'climbing'

        If any class wants to break the naming convention, they should
        set db_name to be the activity without underscores.
        """
        model_name = ContentType.objects.get_for_model(self).model
        activity = model_name[: model_name.rfind('leaderapplication')]
        return 'winter_school' if activity == 'winterschool' else activity

    @staticmethod
    def model_from_activity(activity: enums.Activity) -> type['LeaderApplication']:
        """Get the specific inheriting child from the activity.

        Inverse of activity().
        """
        model = ''.join(activity.value.split('_')).lower() + 'leaderapplication'
        try:
            content_type = ContentType.objects.get(app_label="ws", model=model)
        except ContentType.DoesNotExist as e:
            raise NoApplicationDefined(f"No application for {activity.label}") from e

        model_class = content_type.model_class()
        if model_class is None:
            raise NoApplicationDefined(f"No application for {activity.label}")
        assert issubclass(model_class, LeaderApplication)
        return model_class

    class Meta:
        # Important!!! Child classes must be named: <activity>LeaderApplication
        abstract = True  # See model_from_activity for more
        ordering = ["time_created"]


class HikingLeaderApplication(LeaderApplication):
    desired_rating = models.CharField(
        max_length=10,
        choices=[("Leader", "Leader"), ("Co-Leader", "Co-Leader")],
        help_text="Co-Leader: Can co-lead a 3-season hiking trip with a Leader. "
        "Leader: Can run 3-season hiking trips.",
    )

    mitoc_experience = models.TextField(
        max_length=5000,
        verbose_name="Hiking Experience with MITOC",
        help_text="How long have you been a MITOC member? "
        "Please indicate what official MITOC hikes and Circuses you have been on. "
        "Include approximate dates and locations, number of participants, "
        "trail conditions, type of trip, etc. Give details of whether you participated, "
        "led, or co-led these trips. "
        "[Optional]: If you like, briefly summarize your experience on unofficial trips "
        "or experience outside of New England.",
    )
    formal_training = models.TextField(
        blank=True,
        max_length=5000,
        help_text="Please give details of any medical training and qualifications, with dates. "
        "Also include any other formal outdoor education or qualifications.",
    )
    leadership_experience = models.TextField(
        blank=True,
        max_length=5000,
        verbose_name="Group outdoor/leadership experience",
        help_text="If you've been a leader elsewhere, please describe that here. "
        "This could include leadership in other collegiate outing clubs, "
        "student sports clubs, NOLS, Outward Bound, or AMC; working as a guide, "
        "summer camp counselor, or Scout leader; or organizing hikes with friends.",
    )


class WinterSchoolLeaderApplication(LeaderApplication):
    # Leave ratings long for miscellaneous comments
    # (Omitted from base - some activities might not have users request ratings)
    desired_rating = models.CharField(max_length=255)

    taking_wfa = models.CharField(
        max_length=10,
        choices=[
            ("Yes", "Yes"),
            ("Already", "Already hold WFA or equivalent"),
            ("No", "No"),
            ("Maybe", "Maybe/don't know"),
        ],
        verbose_name="Do you plan on taking a WFA course before Winter School?",
        help_text="You can subsidize your WFA certification by $100 by leading two or more trips! "
        "MITOC holds a WFA course every fall on MIT's campus.",
    )
    training = models.TextField(
        blank=True,
        max_length=5000,
        verbose_name="Formal training and qualifications",
        help_text="Details of any medical, technical, or leadership training and "
        "qualifications relevant to the winter environment, including WFA/WFR if "
        "previously taken. State the approximate dates of these activities. "
        "Leave blank if not applicable.",
    )
    technical_skills = models.TextField(
        blank=True,
        max_length=5000,
        help_text="Please summarize how you meet the criteria for the leader rating you are requesting, "
        "including any relevant technical skills (traction use, navigation, use of overnight equipment, etc.)",
    )
    winter_experience = models.TextField(
        blank=True,
        max_length=5000,
        help_text="Details of previous winter outdoors experience. "
        "Include the type of trip (x-country skiing, above treeline, "
        "snowshoeing, ice climbing, etc), approximate dates and locations, "
        "numbers of participants, notable trail and weather conditions. "
        "Please also give details of whether you participated, led, "
        "or co-led these trips.",
    )
    ice_experience = models.TextField(
        blank=True,
        max_length=5000,
        verbose_name="Ice-climbing experience (ice leader applicants only)",
        help_text="Please describe your ice-climbing experience, "
        "including the approximate number of days you have ice-climbed in the last two years.",
    )
    ski_experience = models.TextField(
        blank=True,
        max_length=5000,
        verbose_name="Ski experience (ski leader applicants only)",
        help_text="Please describe your skiing experience, "
        "including both resort and back-country experience, "
        "and an estimate of the number of days you have backcountry skied in the last two years.",
    )
    other_experience = models.TextField(
        blank=True,
        max_length=5000,
        verbose_name="Other outdoors/leadership experience",
        help_text="Details about any relevant non-winter experience",
    )
    notes_or_comments = models.TextField(
        blank=True,
        max_length=5000,
        help_text="Any relevant details, such as any limitations on availability on "
        "Tue/Thurs nights or weekends during IAP.",
    )

    mentor_activities = models.ManyToManyField(
        MentorActivity,
        blank=True,
        related_name="activities_mentored",
        verbose_name='Which activities would you like to mentor?',
        help_text="Please select at least one.",
    )
    mentee_activities = models.ManyToManyField(
        MentorActivity,
        blank=True,
        related_name="mentee_activities",
        verbose_name='For which activities would you like a mentor?',
        help_text="Please select at least one.",
    )
    mentorship_goals = models.TextField(
        blank=True,
        max_length=5000,
        help_text="What are you looking to get out of the mentorship program?",
    )

    @classmethod
    def can_reapply(cls, latest_application):
        """Participants may only apply once per year to be a WS leader!"""
        return latest_application.year < date_utils.ws_year()


class ClimbingLeaderApplication(LeaderApplication):
    GOOGLE_FORM_ID = '1FAIpQLSeWeIjtQ-p4mH_zGS-YvedvkbmVzBQOarIvzfzBzEgHMKuZzw'

    FAMILIARITY_CHOICES = [
        ('none', "not at all"),
        ('some', "some exposure"),
        ('comfortable', "comfortable"),
        ('very comfortable', "very comfortable"),
    ]

    desired_rating = models.CharField(
        max_length=32,
        choices=[
            ("Bouldering", "Bouldering"),
            ("Single-pitch", "Single-pitch"),
            ("Multi-pitch", "Multi-pitch"),
            ("Bouldering + Single-pitch", "Bouldering + Single-pitch"),
            ("Bouldering + Multi-pitch", "Bouldering + Multi-pitch"),
        ],
    )
    years_climbing = models.IntegerField()
    years_climbing_outside = models.IntegerField()
    outdoor_bouldering_grade = models.CharField(
        max_length=255,
        help_text="At what grade are you comfortable bouldering outside?",
    )
    outdoor_sport_leading_grade = models.CharField(
        max_length=255,
        help_text="At what grade are you comfortable leading outside on sport routes?",
    )
    outdoor_trad_leading_grade = models.CharField(
        max_length=255,
        help_text="At what grade are you comfortable leading outside on trad routes?",
    )

    # How familiar are you with the following...
    familiarity_spotting = models.CharField(
        max_length=16,
        choices=FAMILIARITY_CHOICES,
        verbose_name="Familiarity with spotting boulder problems",
    )
    familiarity_bolt_anchors = models.CharField(
        max_length=16,
        choices=FAMILIARITY_CHOICES,
        verbose_name="Familiarity with 2-bolt 'sport' anchors",
    )
    familiarity_gear_anchors = models.CharField(
        max_length=16,
        choices=FAMILIARITY_CHOICES,
        verbose_name="Familiarity with trad 'gear' anchors",
    )
    familiarity_sr = models.CharField(
        max_length=16,
        choices=FAMILIARITY_CHOICES,
        verbose_name="Familiarity with multi-pitch self-rescue",
    )

    spotting_description = models.TextField(
        blank=True,
        help_text="Describe how you would spot a climber on a meandering tall bouldering problem.",
    )
    tr_anchor_description = models.TextField(
        blank=True,
        verbose_name="Top rope anchor description",
        help_text="Describe how you would build a top-rope anchor at a sport crag.",
    )
    rappel_description = models.TextField(
        blank=True, help_text="Describe how you would set up a safe rappel."
    )
    gear_anchor_description = models.TextField(
        blank=True,
        help_text="Describe what you look for when building a typical gear anchor.",
    )

    formal_training = models.TextField(blank=True)
    teaching_experience = models.TextField(blank=True)
    notable_climbs = models.TextField(
        blank=True,
        help_text="What are some particularly memorable climbs you have done?",
    )
    favorite_route = models.TextField(
        blank=True, help_text="Do you have a favorite route? If so, what is it and why?"
    )

    extra_info = models.TextField(
        blank=True, help_text="Is there anything else you would like us to know?"
    )

    @classmethod
    def google_form_url(cls, embedded=False, participant=None) -> str:
        """For newer applications, they should complete a Google form.

        Return the URL, optionally prefilling participant information or embedding.
        """
        kwargs: dict[str, str] = {}
        if embedded:
            kwargs['embedded'] = 'true'
        if participant:
            # Sadly, Google forms cannot pre-fill an email address.
            # But we can at least pre-fill a name
            kwargs['entry.1371106720'] = participant.name
        return f"https://docs.google.com/forms/d/e/{cls.GOOGLE_FORM_ID}/viewform?{urlencode(kwargs)}"


class DistinctAccounts(models.Model):
    """Pairs of participants that are cleared as potential duplicates."""

    left = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name='distinctions_left'
    )
    right = models.ForeignKey(
        Participant, on_delete=models.CASCADE, related_name='distinctions_right'
    )
