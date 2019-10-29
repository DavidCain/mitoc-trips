import enum

# TODO: Make an abstract base enum that enforces:
# - unique
# - `choices` classmethod


@enum.unique
class Activity(enum.Enum):
    """ An activity for which a leader can be given a rating.

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

    def is_winter_school(self):
        return self == self.WINTER_SCHOOL


@enum.unique
class Program(enum.Enum):
    """ A 'program' is a way to logically group related trips.

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

    # General (official events, courses, TRS, etc.)
    NONE = 'none'

    # Mountain & road biking, taking place *outside* of winter conditions
    BIKING = 'biking'

    # MITOC's boating program: includes kayaking, canoeing, surfing, and more
    # (we could potentially have sub-programs or sub activities, but all ratings are just for boating)
    BOATING = 'boating'

    # Cabin work days (only managers can create for this program)
    CABIN = 'cabin'

    # Climbing trips (taking place *outside* of MRP, or the MITOC Rock Program)
    CLIMBING = 'climbing'

    # Circus events (whole weekend in a cabin with differing types of leaders)
    # NOTE: If this is a Winter Circus, there's ambiguity about the right kind of program
    # future TODO: We should probably allow mixing programs to apply all their rules.
    CIRCUS = 'circus'

    # 3-season hiking (that is, hiking when the WSC has decided winter rules do *not* apply)
    HIKING = 'hiking'

    # MRP - a special program that admits participants & conducts exclusive trips
    MITOC_ROCK_PROGRAM = 'mitoc_rock_program'

    # Service (trail cleanup, watershed cleanup, volunteering, etc.)
    SERVICE = 'service'

    # Winter School *during* IAP (weekend trip part of the normal lottery)
    WINTER_SCHOOL = 'winter_school'
    # Winter School *outside* of IAP (a standalone trip where winter rules apply)
    WINTER_NON_IAP = 'winter_non_iap'

    @classmethod
    def choices(cls):
        """ Group each value into named groups (for use in forms & models). """
        all_choices = [
            (cls.BIKING, 'Biking'),
            (cls.BOATING, 'Boating'),
            (cls.CABIN, 'Cabin'),
            (cls.CLIMBING, 'Climbing'),
            (cls.HIKING, '3-season hiking'),
            (cls.MITOC_ROCK_PROGRAM, 'MITOC Rock Program'),
            (cls.WINTER_SCHOOL, 'Winter School'),
            (cls.WINTER_NON_IAP, 'Winter (outside IAP)'),
            # Open options!
            (cls.CIRCUS, 'Circus'),
            (cls.SERVICE, 'Service'),
            (cls.NONE, 'None'),
        ]

        open_choices, closed_choices = [], []
        for program, label in all_choices:
            if cls._is_open(program):
                open_choices.append((program.value, label))
            else:
                closed_choices.append((program.value, label))

        return [
            ('Specific rating required', closed_choices),
            ('Any leader rating allowed', open_choices),
        ]

    def is_open(self):
        """ Return if this program allows any leader to create trips. """
        return self._is_open(self.value)

    @classmethod
    def _is_open(cls, value):
        """ Return True if any leader can lead. """
        return cls(value) in (cls.CIRCUS, cls.SERVICE, cls.NONE)

    def required_activity(self):
        """ For the program, return a required leader rating to make trips.

        Returns None otherwise.
        """
        mapping = {
            self.BIKING: Activity.BIKING,
            self.BOATING: Activity.BOATING,
            self.CABIN: Activity.CABIN,  # TODO: Remove 'cabin' as a rating
            self.CLIMBING: Activity.CLIMBING,
            self.HIKING: Activity.HIKING,
            self.MITOC_ROCK_PROGRAM: Activity.CLIMBING,
            self.WINTER_SCHOOL: Activity.WINTER_SCHOOL,
            self.WINTER_NON_IAP: Activity.WINTER_SCHOOL,
            # No specific rating required, just _any_ rating
            self.CIRCUS: None,
            self.SERVICE: None,
            self.NONE: None,
        }
        return mapping[self]


@enum.unique
class TripType(enum.Enum):
    """ A descriptor for what sort of things will be done on a trip.

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

    @classmethod
    def choices(cls):
        """ Group into logical blocks for easy identification.

        In the future, we may tightly activity ratings with the options you can select below.
        """
        return [
            (
                'Biking',
                [
                    (cls.ROAD_BIKING.value, 'Road biking'),
                    (cls.MOUNTAIN_BIKING.value, 'Mountain biking'),
                ],
            ),
            (
                'Boating',
                [
                    (cls.CANOEING.value, 'Canoeing'),
                    (cls.KAYAKING.value, 'Kayaking'),
                    (cls.SEA_KAYAKING.value, 'Sea kayaking'),
                    (cls.SURFING.value, 'Surfing'),
                ],
            ),
            (
                'Climbing',
                [
                    (cls.BOULDERING.value, 'Bouldering'),
                    (cls.GYM_CLIMBING.value, 'Gym climbing'),
                    (cls.ICE_CLIMBING.value, 'Ice climbing'),
                    (cls.SPORT_CLIMBING.value, 'Sport climbing, top rope'),
                    (cls.TRAD_CLIMBING.value, 'Trad climbing'),
                ],
            ),
            (
                'Hiking',
                [
                    (cls.HIKING.value, 'Hiking'),
                    (cls.TRAIL_RUNNING.value, 'Trail running'),
                ],
            ),
            (
                'Skiing',
                [
                    (cls.BC_SKIING.value, 'Backcountry skiing'),
                    (cls.XC_SKIING.value, 'Cross-country skiing'),
                    (cls.RESORT_SKIING.value, 'Resort skiing'),
                ],
            ),
            (
                'Miscellaneous',
                [
                    (cls.ICE_SKATING.value, 'Ice skating'),
                    (cls.ULTIMATE.value, 'Ultimate'),
                ],
            ),
            (
                'Other, N/A',
                [
                    (cls.NONE.value, 'None, or not applicable'),
                    (cls.OTHER.value, 'Other'),
                ],
            ),
        ]
