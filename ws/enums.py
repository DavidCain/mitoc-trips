import enum

# TODO: Make an abstract base enum that enforces:
# - unique
# - `choices` classmethod


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
