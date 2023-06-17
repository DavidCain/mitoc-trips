import re
from typing import NamedTuple

from django.db import migrations


class TripChange(NamedTuple):
    old_level: str
    new_level: str


VALID_LEVELS = {
    'A',
    'B',
    'C',
    'AS',
    'BS',
    'CS',
    'AI',
    'BI',
    'CI',
    # Rare, but possible!
    # At time of writing, no trips exist that do skiing & ice climbing.
    'AIS',
    'BIS',
    'CIS',
}
updates: dict[int, TripChange] = {
    304: TripChange('B (below treeline), overnight', 'B'),
    314: TripChange('I', 'AI'),  # Flume
    958: TripChange('I', 'AI'),  # Flume
    337: TripChange('I', 'AI'),  # Rumney Ice
    890: TripChange('I', 'AI'),  # Rumney Ice
    644: TripChange('I', 'AI'),  # Rumney Ice
    354: TripChange('I', 'AI'),  # Frankenstein
    355: TripChange('I', 'AI'),  # Frankenstein
    581: TripChange('I', 'AI'),  # Arethusa
    584: TripChange('B/C', 'BS'),
    625: TripChange('A and S', 'AS'),
    626: TripChange('A and S', 'AS'),
    864: TripChange('Beginner/ Intermediate', 'AS'),  # resort XC skiing
    895: TripChange('I', 'AI'),  # Frankenstein
    923: TripChange('I', 'AI'),  # Frankenstein
    1220: TripChange('B - below tree line', 'B'),
    1234: TripChange('S-', 'BS'),
    1274: TripChange('Beginner/ Intermediate', 'AS'),  # resort XC skiing
    1346: TripChange('Cohort', 'AI'),  # Echo Crag trip, 'difficulty' is "Ai"
    1347: TripChange('Previous winter hiking experience', 'C'),
    1195: TripChange('BI (or perhaps AI, depending on conditions and interest)', 'BI'),
    1196: TripChange(
        'BI (or perhaps AI depending on conditions and participant interests)', 'BI'
    ),
}


def make_levels_consistent(apps, schema_editor):
    """Change all old WS trips with a known level to have valid levels."""
    Trip = apps.get_model("ws", "Trip")

    def _trips_with_punctuation_changes():
        normal_chars = set('ABCIS')
        special_chars = re.compile(r'[+ ,/\.-]')
        expected_chars = set('ABCIS+/,-. ').union(normal_chars)

        normalization_needed = (
            Trip.objects.exclude(level__isnull=True)
            .exclude(level__in='ABC')
            .exclude(level='Unknown')  # old trips
        )
        characters_seen = set()

        trips = []
        for trip in normalization_needed.exclude(pk__in=updates):
            if (
                normal_chars.issuperset(trip.level)
                and ''.join(sorted(trip.level)) == trip.level
            ):
                continue  # already reads AI, BI, CS, etc.
            trips.append(trip)
            characters_seen.update(set(trip.level))

        assert characters_seen.issubset(expected_chars), str(characters_seen)

        for trip in trips:
            new_level = ''.join(sorted(re.sub(special_chars, '', trip.level)))
            trip.level = new_level

        return trips

    trips_to_update = []

    for trip in Trip.objects.filter(pk__in=updates):
        assert trip.level == updates[trip.pk].old_level, f"Unexpected {trip.level}"

        trip.level = updates[trip.pk].new_level
        trips_to_update.append(trip)

    for trip in _trips_with_punctuation_changes():
        trips_to_update.append(trip)

    # Sanity check: our massaging should have resulted in consistency!
    for trip in trips_to_update:
        assert trip.level in VALID_LEVELS, f"Did not expect {trip.level}"

    Trip.objects.bulk_update(trips_to_update, ['level'])

    all_level_trips = Trip.objects.exclude(level='Unknown').exclude(level__isnull=True)

    # Final sanity check -- our migration should have worked if we've fixed all levels
    for bad_trip in all_level_trips.exclude(level__in=VALID_LEVELS):
        if bad_trip.pk not in updates:
            raise ValueError(f"Found a bad trip! {bad_trip.pk} {bad_trip}")


class Migration(migrations.Migration):
    dependencies = [
        ('ws', '0050_trip_reimbursement'),
    ]

    operations = [migrations.RunPython(make_levels_consistent)]
