import enum
from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode

from django.urls import reverse
from django.utils.safestring import mark_safe

if TYPE_CHECKING:
    from ws.models import Trip


# TODO: Make an abstract base enum that enforces:
# - unique
# - `choices` classmethod


@enum.unique
class ProfileProblem(enum.Enum):
    """A problem with the participant's profile that must be corrected."""

    NO_INFO = 1  # No Participant object!
    STALE_INFO = 2  # Hasn't been updated lately. Medical info may have been scrubbed!
    LEGACY_AFFILIATION = 3  # 'S' (student of ambiguous MIT affiliation)
    INVALID_EMERGENCY_CONTACT_PHONE = 4  # (typically just a blank contact #)
    MISSING_FULL_NAME = 5  # 'Cher' instead of 'Cherilyn Sarkisian'
    PRIMARY_EMAIL_NOT_VALIDATED = 6  # No validated emails, or deleted primary

    @property
    def how_to_fix(self):
        """Return a message with instructions (to the user) on how to fix the problem.

        This includes URLs and should be marked as safe if for rendering in HTML.
        """
        manage_emails = reverse('account_email')
        mapping = {
            self.NO_INFO: 'Please complete this important safety information to finish the signup process.',
            self.STALE_INFO: (
                "You haven't updated your personal information in a while. "
                "Please ensure that the below information is correct and click 'Submit' to update!"
            ),
            self.LEGACY_AFFILIATION: 'Please update your MIT affiliation.',
            self.INVALID_EMERGENCY_CONTACT_PHONE: 'Please supply a valid number for your emergency contact.',
            self.MISSING_FULL_NAME: 'Please supply your full legal name.',
            self.PRIMARY_EMAIL_NOT_VALIDATED: f'Please <a href="{manage_emails}">verify your email address</a>',
        }
        return mapping[self]


@enum.unique
class TripIneligibilityReason(enum.Enum):
    """A (correctable) reason why a participant cannot attend a trip.

    Each of these problems is a barrier to a participant being on a trip,
    but includes a solution as to how they can fix the problem.
    For example, if they have an expired waiver, we tell the participant
    how to sign a new one.

    There are some problems that prohibit a participant from signing up,
    but do *not* have an immediate solution. For example, if the participant
    is already on the trip (as a leader or participant), they can't sign up,
    but they also don't *need* to "fix" that problem.
    """

    # User is not logged in (we require a Participant object to sign up)
    NOT_LOGGED_IN = 1

    # User is logged in, but lacks a corresponding participant profile
    NO_PROFILE_INFO = 2

    # The participant is the WIMP on the trip, and should not attend it.
    IS_TRIP_WIMP = 3

    # Specific to Program.WINTER_SCHOOL -- participant hasn't attended lectures, and it's required
    MISSED_WS_LECTURES = 4

    # A ProfileProblem exists for this user
    PROFILE_PROBLEM = 5

    # The participant has never been a MITOC member or had a waiver before
    MEMBERSHIP_MISSING = 6
    WAIVER_MISSING = 7

    # Membership or waiver already exist, but must be renewed, either because:
    # 1. they've expired
    # 2. they will have expired by the time the trip starts (and we can renew today)
    WAIVER_NEEDS_RENEWAL = 8
    MEMBERSHIP_NEEDS_RENEWAL = 9

    @property
    def related_to_membership(self):
        """Return if this problem relates to the MITOCer's membership.

        Useful for determining if we need to hit the membership database to refresh
        the cache in the case of a problem preventing trip attendance.
        """
        return self in {
            self.MEMBERSHIP_MISSING,
            self.MEMBERSHIP_NEEDS_RENEWAL,
            self.WAIVER_MISSING,
            self.WAIVER_NEEDS_RENEWAL,
        }

    @property
    def label(self):
        """A generic label to be read by any consumer (i.e. the user, or another leader)."""
        mapping = {
            self.NOT_LOGGED_IN: 'Not logged in!',
            self.NO_PROFILE_INFO: 'No profile found!',
            self.IS_TRIP_WIMP: 'Cannot attend a trip as its WIMP',
            self.MISSED_WS_LECTURES: 'Must have attended mandatory safety lectures',
            self.PROFILE_PROBLEM: 'Profile requires modification',
            self.MEMBERSHIP_MISSING: 'An active membership is required',
            self.MEMBERSHIP_NEEDS_RENEWAL: 'Membership must be renewed',
            self.WAIVER_MISSING: 'A current waiver is required',
            self.WAIVER_NEEDS_RENEWAL: 'Waiver must be renewed',
        }
        return mapping[self]

    def how_to_fix_for(self, trip: 'Trip') -> str:
        """Return a message directed at the user with the problem containing clues on how to fix.

        This includes URLs and should be marked as safe if for rendering in HTML.
        """
        dt = trip.trip_date
        trip_date = f'{dt:%B} {dt.day}, {dt.year}'

        edit_profile = reverse('edit_profile')
        account_login = (
            reverse('account_login')
            + '?'
            # Probably overkill... f'?next=/trips/{trip.pk}' is plenty, but this is a better pattern
            # (We'll be marking this string as safe, so the URL *must* be escaped to avoid injection)
            + urlencode({'next': reverse('view_trip', args=(trip.pk,))})
        )
        pay_dues = reverse('pay_dues')
        initiate_waiver = reverse('initiate_waiver')

        # "you must... "
        mapping: dict[int, str] = {
            self.NOT_LOGGED_IN: f'<a href="{account_login}">log in</a>',
            self.NO_PROFILE_INFO: f'provide <a href="{edit_profile}">personal information</a>',
            self.IS_TRIP_WIMP: 'be replaced in your role as the trip WIMP',
            self.PROFILE_PROBLEM: f'update your <a href="{edit_profile}">personal information</a>',
            self.MISSED_WS_LECTURES: '''have attended this year's lectures. Questions? Contact the <a href="mailto:ws-chair@mit.edu">Winter School Chair</a>.''',
            self.MEMBERSHIP_MISSING: f'have an <a href="{pay_dues}">active membership</a>',
            self.MEMBERSHIP_NEEDS_RENEWAL: f'''have a <a href="{pay_dues}">membership that's valid until at least {trip_date}</a>''',
            self.WAIVER_MISSING: f'<a href="{initiate_waiver}">sign a waiver</a>',
            self.WAIVER_NEEDS_RENEWAL: f'''have a <a href="{initiate_waiver}">waiver that's valid until at least {trip_date}</a>''',
        }
        typed_mapping = cast(dict[TripIneligibilityReason, str], mapping)
        return mark_safe(typed_mapping[self])  # noqa: S308


@enum.unique
class Activity(enum.Enum):
    """An activity for which a leader can be given a rating.

    Identifying characteristics of an activity:
        - There are one or more chairs that handle rating leaders
        - The rating is a requirement for creating trips in at least one Program
        - Having a rating means the leader has demonstrated skill & experience
          allowing them to safely bring participants along on this type of trip.
    """

    BIKING = 'biking'
    BOATING = 'boating'
    CABIN = 'cabin'  # TODO: somewhat of an exception to the above criteria
    CLIMBING = 'climbing'
    HIKING = 'hiking'
    WINTER_SCHOOL = 'winter_school'

    @property
    def label(self):
        mapping = {
            self.BIKING: 'Biking',
            self.BOATING: 'Boating',
            self.CABIN: 'Cabin',
            self.CLIMBING: 'Climbing',
            self.HIKING: 'Hiking',
            self.WINTER_SCHOOL: 'Winter School',
        }
        return mapping[self]

    def is_winter_school(self) -> bool:
        return self == Activity(self.WINTER_SCHOOL)


@enum.unique
class Program(enum.Enum):
    """A 'program' is a way to logically group related trips.

    For example, during January, most trips are part of the Winter School program.
    With this classification comes some special different behavior:

    - WS Lecture attendance is required to join the trip
    - Special rules apply for when itineraries must be submitted
    - Trip placement is done via a special, weekly, multi-trip lottery
      (Lottery behavior is described elsewhere, but this has participants rank
      their trips, and places each participant on, at most, one trip that weekend).

    Winter trips taking place *outside* of IAP have differing behavior. Leaders
    must have a rating granted by the Winter Safety Committee, but the trip
    does *not* have the same multi-trip lottery behavior.

    Programs allow us to separate three related concepts:
    - A leader's ability to create & run the trip (see: LeaderRating)
    - The type of activity that will be done on the trip
    - The rules & behavior that should apply for the trip (Program)
    """

    # Mountain & road biking, taking place *outside* of winter conditions
    BIKING = 'biking'

    # MITOC's boating program: includes kayaking, canoeing, surfing, and more
    # (we could potentially have sub-programs or sub activities, but all ratings are just for boating)
    BOATING = 'boating'

    # Cabin work days (only managers can create for this program)
    CABIN = 'cabin'

    # Climbing trips (taking place *outside* of School of Rock)
    CLIMBING = 'climbing'

    # 3-season hiking (that is, hiking when the WSC has decided winter rules do *not* apply)
    HIKING = 'hiking'

    # School of Rock - a special program that admits participants & conducts exclusive trips
    SCHOOL_OF_ROCK = 'mitoc_rock_program'  # (formerly known as the MRP)

    # Winter School *during* IAP (weekend trip part of the normal lottery)
    WINTER_SCHOOL = 'winter_school'
    # Winter School *outside* of IAP (a standalone trip where winter rules apply)
    WINTER_NON_IAP = 'winter_non_iap'

    # Circus events (whole weekend in a cabin with differing types of leaders)
    # NOTE: If this is a Winter Circus, there's ambiguity about the right kind of program
    # future TODO: We should probably allow mixing programs to apply all their rules.
    CIRCUS = 'circus'

    # Service (trail cleanup, watershed cleanup, volunteering, etc.)
    SERVICE = 'service'

    # General (official events, courses, TRS, etc.)
    NONE = 'none'

    @property
    def label(self):
        mapping = {
            self.BIKING: 'Biking',
            self.BOATING: 'Boating',
            self.CABIN: 'Cabin',
            self.CLIMBING: 'Climbing',
            self.HIKING: '3-season hiking',
            self.SCHOOL_OF_ROCK: 'School of Rock',
            self.WINTER_SCHOOL: 'Winter School',
            self.WINTER_NON_IAP: 'Winter (outside IAP)',
            # Open options!
            self.CIRCUS: 'Circus',
            self.SERVICE: 'Service',
            self.NONE: 'None',
        }
        return mapping[self]

    @classmethod
    def choices(
        cls,
    ) -> tuple[
        tuple[str, list[tuple[str, str]]],  # Specific rating
        tuple[str, list[tuple[str, str]]],  # Any rating allowed
    ]:
        """Group each value into named groups (for use in forms & models)."""
        ordered_choices = [
            cls.BIKING,
            cls.BOATING,
            cls.CABIN,
            cls.CLIMBING,
            cls.HIKING,
            cls.SCHOOL_OF_ROCK,
            cls.WINTER_SCHOOL,
            cls.WINTER_NON_IAP,
            # Open options!
            cls.CIRCUS,
            cls.SERVICE,
            cls.NONE,
        ]

        open_choices, closed_choices = [], []
        for program_enum in ordered_choices:
            if program_enum.is_open():
                open_choices.append((program_enum.value, program_enum.label))
            else:
                closed_choices.append((program_enum.value, program_enum.label))

        return (
            ('Specific rating required', closed_choices),
            ('Any leader rating allowed', open_choices),
        )

    def is_open(self) -> bool:
        """Return if this program allows any leader to create trips."""
        return self._is_open(self.value)

    @classmethod
    def _is_open(cls, value: str) -> bool:
        """Return True if any leader can lead."""
        return cls(value) in (cls.CIRCUS, cls.SERVICE, cls.NONE)

    def is_winter_school(self) -> bool:
        return self == Program(self.WINTER_SCHOOL)

    def winter_rules_apply(self) -> bool:
        return self in (Program(self.WINTER_SCHOOL), Program(self.WINTER_NON_IAP))

    def required_activity(self) -> Activity | None:
        """For the program, return a required leader rating to make trips.

        Returns None otherwise.
        """
        return REQUIRED_ACTIVITY_BY_PROGRAM[self]


REQUIRED_ACTIVITY_BY_PROGRAM: Mapping[Program, Activity | None] = MappingProxyType(
    {
        Program.BIKING: Activity.BIKING,
        Program.BOATING: Activity.BOATING,
        Program.CABIN: Activity.CABIN,  # TODO: Remove 'cabin' as a rating
        Program.CLIMBING: Activity.CLIMBING,
        Program.HIKING: Activity.HIKING,
        Program.SCHOOL_OF_ROCK: Activity.CLIMBING,
        Program.WINTER_SCHOOL: Activity.WINTER_SCHOOL,
        Program.WINTER_NON_IAP: Activity.WINTER_SCHOOL,
        # No specific rating required, just _any_ rating
        Program.CIRCUS: None,
        Program.SERVICE: None,
        Program.NONE: None,
    }
)


@enum.unique
class TripType(enum.Enum):
    """A descriptor for what sort of things will be done on a trip.

    This is distinct from leader ratings, which pertain to a certain class of activity.
    """

    # Catchall for when the activity isn't described, or none make sense
    NONE = 'none'
    OTHER = 'other'

    # Biking
    ROAD_BIKING = 'biking_road'
    MOUNTAIN_BIKING = 'biking_mountain'

    # Boating
    KAYAKING = 'boating_kayaking'
    SEA_KAYAKING = 'boating_kayaking_sea'
    CANOEING = 'boating_canoeing'
    SURFING = 'boating_surfing'

    # Climbing
    BOULDERING = 'climbing_bouldering'
    ICE_CLIMBING = 'climbing_ice'
    SPORT_CLIMBING = 'climbing_sport'
    TRAD_CLIMBING = 'climbing_trad'
    GYM_CLIMBING = 'climbing_gym'

    # Hiking
    HIKING = 'hiking_hiking'
    TRAIL_RUNNING = 'hiking_trail_running'

    # Skiing!
    RESORT_SKIING = 'skiing_resort'
    BC_SKIING = 'skiing_bc'
    XC_SKIING = 'skiing_xc'

    # Miscellaneous
    ICE_SKATING = 'ice_skating'
    ULTIMATE = 'ultimate'
    YOGA = 'yoga'

    @property
    def label(self):
        mapping = {
            self.BC_SKIING: 'Backcountry skiing',
            self.BOULDERING: 'Bouldering',
            self.CANOEING: 'Canoeing',
            self.GYM_CLIMBING: 'Gym climbing',
            self.HIKING: 'Hiking',
            self.ICE_CLIMBING: 'Ice climbing',
            self.ICE_SKATING: 'Ice skating',
            self.KAYAKING: 'Kayaking',
            self.MOUNTAIN_BIKING: 'Mountain biking',
            self.NONE: 'None, or not applicable',
            self.OTHER: 'Other',
            self.RESORT_SKIING: 'Resort skiing',
            self.ROAD_BIKING: 'Road biking',
            self.SEA_KAYAKING: 'Sea kayaking',
            self.SPORT_CLIMBING: 'Sport climbing, top rope',
            self.SURFING: 'Surfing',
            self.TRAD_CLIMBING: 'Trad climbing',
            self.TRAIL_RUNNING: 'Trail running',
            self.ULTIMATE: 'Ultimate',
            self.XC_SKIING: 'Cross-country skiing',
            self.YOGA: 'Yoga',
        }
        return mapping[self]

    @classmethod
    def _categorized(cls) -> dict[str, list['TripType']]:
        return {
            'Biking': [
                cls.ROAD_BIKING,
                cls.MOUNTAIN_BIKING,
            ],
            'Boating': [
                cls.CANOEING,
                cls.KAYAKING,
                cls.SEA_KAYAKING,
                cls.SURFING,
            ],
            'Climbing': [
                cls.BOULDERING,
                cls.GYM_CLIMBING,
                cls.ICE_CLIMBING,
                cls.SPORT_CLIMBING,
                cls.TRAD_CLIMBING,
            ],
            'Hiking': [
                cls.HIKING,
                cls.TRAIL_RUNNING,
            ],
            'Skiing': [
                cls.BC_SKIING,
                cls.XC_SKIING,
                cls.RESORT_SKIING,
            ],
            'Miscellaneous': [
                cls.ICE_SKATING,
                cls.ULTIMATE,
                cls.YOGA,
            ],
            'Other, N/A': [
                cls.NONE,
                cls.OTHER,
            ],
        }

    @classmethod
    def choices(cls) -> list[tuple[str, list[tuple[str, str]]]]:
        """Group into logical blocks for easy identification.

        In the future, we may tightly activity ratings with the options you can select below.
        """
        return [
            (category, [(trip_type.value, trip_type.label) for trip_type in trip_types])
            for category, trip_types in cls._categorized().items()
        ]
