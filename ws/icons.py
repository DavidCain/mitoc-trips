from collections.abc import Mapping
from types import MappingProxyType

from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

from ws import models
from ws.enums import Program, TripType

# If the trip is under this program, *always* use icon, regardless of trip type
PRIMARY_PROGRAMS = frozenset([Program.SERVICE, Program.SCHOOL_OF_ROCK])

ICON_BY_TRIP_TYPE: Mapping[TripType, str] = MappingProxyType(
    {
        TripType.HIKING: "hiking",
        TripType.TRAIL_RUNNING: "running",
        TripType.BC_SKIING: "skiing",
        TripType.XC_SKIING: "skiing-nordic",
        TripType.RESORT_SKIING: "skiing",  # pro has `ski-lift`
        TripType.ICE_SKATING: "skating",  # pro has `ice-skate`
        TripType.ICE_CLIMBING: "icicles",
        TripType.SURFING: "swimmer",
        TripType.ULTIMATE: "compact-disc",  # close enough
        TripType.GYM_CLIMBING: "hand-rock",
        TripType.SPORT_CLIMBING: "hand-rock",
        TripType.TRAD_CLIMBING: "hand-rock",
        TripType.BOULDERING: "hands",  # kinda looks like a spotter?
        TripType.MOUNTAIN_BIKING: "biking",  # pro has `biking-mountain`
        TripType.ROAD_BIKING: "biking",
        TripType.YOGA: "om",
    }
)

# Exhaustive mapping of every program to a distinct icon
ICON_BY_PROGRAM: Mapping[Program, str] = MappingProxyType(
    {
        Program.BIKING: "biking",  # pro has `biking-mountain`
        Program.BOATING: "water",
        Program.CABIN: "home",
        Program.CIRCUS: "users",
        Program.CLIMBING: "hand-rock",  # (use regular with `far`)
        Program.HIKING: "hiking",
        Program.SCHOOL_OF_ROCK: "school",
        Program.SERVICE: "hands-helping",
        Program.WINTER_NON_IAP: "snowman",
        Program.WINTER_SCHOOL: "snowflake",
        # No icon for the 'none' program
        Program.NONE: "",
    }
)


def fa_icon_for_trip(trip: models.Trip) -> str:
    """Return a FontAwesome icon that best describes this trip."""
    # Always give the same icon to certain programs
    if trip.program_enum in PRIMARY_PROGRAMS:
        return ICON_BY_PROGRAM[trip.program_enum]

    # Start with the trip types that have specific icons
    if trip.trip_type_enum in ICON_BY_TRIP_TYPE:
        return ICON_BY_TRIP_TYPE[trip.trip_type_enum]

    # After that, fall back to programs
    return ICON_BY_PROGRAM[trip.program_enum]


def _describe(trip: models.Trip) -> str:
    """Return a simple string describing the trip."""
    if trip.trip_type_enum in {TripType.NONE, TripType.OTHER}:
        return trip.get_program_display()
    return trip.get_trip_type_display()


def for_trip(trip: models.Trip) -> SafeString:
    """Return (safe) HTML with an icon that describes the trip."""
    icon = fa_icon_for_trip(trip)
    if not icon:
        return mark_safe("")  # (For consistent return type)
    solid_regular = "far" if icon == "hand-rock" else "fa"
    title = escape(_describe(trip))
    html = f'<i class="{solid_regular} fa-fw fa-{icon}" title="{title}"></i>'
    return mark_safe(html)  # noqa: S308
