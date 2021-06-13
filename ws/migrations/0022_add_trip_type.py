from django.db import migrations, models

from ws.enums import TripType

# Map from the old activities to their new corresponding activity
# In many cases, is not as detailed as we'd like.
# See `MANUAL_ACTIVITIES` for a hand-curated mapping.
ACTIVITY_TO_TRIP_TYPE = {
    'cabin': TripType.NONE,
    'course': TripType.NONE,
    'official_event': TripType.NONE,
    'circus': TripType.NONE,
    # Not actually going to be universally accurate, but the most common activity per program
    'hiking': TripType.HIKING,
    'biking': TripType.MOUNTAIN_BIKING,
    'climbing': TripType.SPORT_CLIMBING,
    'boating': TripType.KAYAKING,
    'winter_school': TripType.HIKING,
}


# fmt: off
METRO_ROCK_TRIPS = [
    186, 221, 232, 237, 241, 246, 253, 258, 259, 260, 261, 263, 364, 372, 375, 376, 379,
    393, 399, 406, 408, 417, 428, 433, 439, 443, 447, 449, 453, 458, 463, 472, 480, 484,
    485, 496, 503, 508, 517, 518, 519, 521, 522, 531, 535, 585, 636, 640, 669, 671, 672,
    674, 676, 680, 682, 695, 697, 699, 702, 709, 716, 719, 725, 730, 738, 758, 762, 764,
    765, 772, 779, 783, 784, 786, 788, 790, 794, 800, 802, 805, 809, 813, 817, 819, 820,
    823, 828, 829, 834, 835, 848, 892, 950, 953, 983, 991, 996, 1002, 1007, 1009, 1013,
    1024, 1030, 1033, 1038, 1064, 1076, 1082, 1086, 1088, 1100, 1107, 1113, 1117, 1132,
    1137, 1152, 1156, 1160, 1175,
]

# Trips that were manually inspected to get activity
MANUAL_ACTIVITIES = {
    TripType.NONE: [
        164
    ],
    TripType.HIKING: [
        993, 999
    ],
    TripType.SEA_KAYAKING: [
        196, 202, 213, 1098, 1101, 1122
    ],
    TripType.CANOEING: [
        195, 236, 240, 397, 791
    ],
    TripType.SURFING: [
        201, 214, 238, 732
    ],
    TripType.BOULDERING: [
        735, 1174
    ],
    TripType.ULTIMATE: [
        1119, 1093, 1079, 1065
    ],
    TripType.ICE_SKATING: [
        45, 580, 670, 965
    ],
    TripType.TRAIL_RUNNING: [
        698, 922, 995, 1006, 1077, 1106, 1108, 1109, 1110, 1111, 1118, 1123,
        1124, 1125, 1138, 1139, 1140, 1141, 1171,
    ],
    TripType.SPORT_CLIMBING: [
        199, 215, 1029
    ],
    TripType.TRAD_CLIMBING: [
        227, 251, 252, 434, 493, 498, 504, 705, 708, 806, 1049, 1050, 1054,
        1057, 1061, 1063,
    ],
    TripType.GYM_CLIMBING: [
        *METRO_ROCK_TRIPS
    ],
    TripType.ICE_CLIMBING: [
        24, 25, 26, 27, 28, 29, 31, 33, 50, 52, 59, 62, 67, 68, 78, 94, 108,
        109, 110, 116, 132, 135, 136, 147, 153, 174, 266, 270, 271, 296, 297,
        298, 309, 314, 319, 327, 337, 338, 339, 340, 354, 355, 388, 530, 537,
        528, 529, 539, 540, 541, 542, 566, 581, 583, 610, 615, 616, 617, 638,
        641, 642, 644, 831, 832, 849, 853, 887, 890, 895, 897, 919, 923, 958,
        972, 979,
    ],
    TripType.RESORT_SKIING: [
        333, 625, 626, 889, 998, 1004
    ],
    TripType.ROAD_BIKING: [
        445, 1112, 1092, 712, 495
    ],
    TripType.MOUNTAIN_BIKING: [
        17, 103, 123, 154, 282, 407, 432, 438, 473, 476, 477, 603, 667,
    ],
    TripType.BC_SKIING: [
        71, 91, 137, 140, 148, 161, 277, 313, 328, 348, 356, 358, 391, 392,
        394, 562, 584, 588, 594, 601, 632, 650, 652, 656, 662, 675, 838, 855,
        862, 870, 888, 891, 912, 949, 959, 961, 975, 989,
    ],
    TripType.XC_SKIING: [
        11, 48, 76, 89, 127, 146, 290, 334, 341, 357, 383, 579, 624, 629, 637,
        649, 659, 662, 687, 863, 864, 872, 903, 915, 926, 962, 977, 1019,
    ],
}
# fmt: on


def set_trip_type(apps, schema_editor):
    """Migrate some activity types to use a program, don't trigger signals."""
    Trip = apps.get_model('ws', 'Trip')

    for activity, trip_type in ACTIVITY_TO_TRIP_TYPE.items():
        Trip.objects.filter(activity=activity).update(trip_type=trip_type.value)
    for trip_type, pks in MANUAL_ACTIVITIES.items():
        Trip.objects.filter(pk__in=pks).update(trip_type=trip_type.value)


def clear_trip_type(apps, schema_editor):
    Trip = apps.get_model('ws', 'Trip')
    Trip.objects.update(trip_type="")


class Migration(migrations.Migration):

    dependencies = [('ws', '0021_trip_program')]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='trip_type',
            field=models.CharField(
                default='none',
                choices=[
                    (
                        'Biking',
                        [
                            ('biking_road', 'Road biking'),
                            ('biking_mountain', 'Mountain biking'),
                        ],
                    ),
                    (
                        'Boating',
                        [
                            ('boating_canoeing', 'Canoeing'),
                            ('boating_kayaking', 'Kayaking'),
                            ('boating_kayaking_sea', 'Sea kayaking'),
                            ('boating_surfing', 'Surfing'),
                        ],
                    ),
                    (
                        'Climbing',
                        [
                            ('climbing_bouldering', 'Bouldering'),
                            ('climbing_gym', 'Gym climbing'),
                            ('climbing_ice', 'Ice climbing'),
                            ('climbing_sport', 'Sport climbing, top rope'),
                            ('climbing_trad', 'Trad climbing'),
                        ],
                    ),
                    (
                        'Hiking',
                        [
                            ('hiking_hiking', 'Hiking'),
                            ('hiking_trail_running', 'Trail running'),
                        ],
                    ),
                    (
                        'Skiing',
                        [
                            ('skiing_bc', 'Backcountry skiing'),
                            ('skiing_xc', 'Cross-country skiing'),
                            ('skiing_resort', 'Resort skiing'),
                        ],
                    ),
                    (
                        'Miscellaneous',
                        [('ice_skating', 'Ice skating'), ('ultimate', 'Ultimate')],
                    ),
                    (
                        'Other, N/A',
                        [('none', 'None, or not applicable'), ('other', 'Other')],
                    ),
                ],
                max_length=255,
            ),
        ),
        migrations.RunPython(set_trip_type, reverse_code=clear_trip_type),
    ]
