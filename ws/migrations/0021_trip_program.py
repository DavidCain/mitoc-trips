from django.db import migrations, models
from django.db.models import Q

# Once made, enum names should be constant. It's generally safe to reference these.
# On the other hand, activity names will be changed, so use strings
from ws.enums import Program

# A mapping for each activity that has one exact corresponding program
ACTIVITY_TO_PROGRAM = {
    'cabin': Program.CABIN.value,
    'winter_school': Program.WINTER_SCHOOL.value,
    'biking': Program.BIKING.value,
    'boating': Program.BOATING.value,
    'circus': Program.CIRCUS.value,
    'climbing': Program.CLIMBING.value,
    'hiking': Program.HIKING.value,
    # Multiple 'none' types!
    'course': Program.NONE.value,
    'official_event': Program.NONE.value,
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

MANUAL_MAPPING = {
    Program.NONE: [
        514, 808, 825, 1066, 1070, 1104, 1149, 1163, 1164, 1165, 1166,
        *METRO_ROCK_TRIPS,
    ],
    Program.SERVICE: [
        514, 808, 825, 1066, 1070, 1104, 1149, 1163, 1164, 1165, 1166
    ],
    Program.WINTER_NON_IAP: [
        164, 174, 377, 378, 382, 384, 385, 388, 389, 528, 529, 532, 538, 685,
        686, 687, 688, 690, 830, 831, 832, 993, 1000, 1018, 1019, 1021, 1022,
    ],
}
# fmt: on


def migrate_activity_to_program(apps, schema_editor):
    """Migrate some activity types to use a program, don't trigger signals."""
    Trip = apps.get_model('ws', 'Trip')
    for activity, program in ACTIVITY_TO_PROGRAM.items():
        Trip.objects.filter(activity=activity).update(program=program)

    # (All SoR trips spot-checked to have these tags, with no false positives)
    Trip.objects.filter(
        Q(name__contains='MRP')
        | Q(name__contains='SoR')
        | Q(name__contains='School of Rock')
    ).update(program='mitoc_rock_program')

    for program, pks in MANUAL_MAPPING.items():
        Trip.objects.filter(pk__in=pks).update(program=program.value)


def do_nothing(*args):
    pass


class Migration(migrations.Migration):
    dependencies = [('ws', '0020_typo_corrections')]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='program',
            field=models.CharField(
                default='none',
                choices=[
                    (
                        'Specific rating required',
                        [
                            ('biking', 'Biking'),
                            ('boating', 'Boating'),
                            ('cabin', 'Cabin'),
                            ('climbing', 'Climbing'),
                            ('hiking', '3-season hiking'),
                            ('mitoc_rock_program', 'MITOC Rock Program'),
                            ('winter_school', 'Winter School'),
                            ('winter_non_iap', 'Winter (outside IAP)'),
                        ],
                    ),
                    (
                        'Any leader rating allowed',
                        [
                            ('circus', 'Circus'),
                            ('service', 'Service'),
                            ('none', 'None'),
                        ],
                    ),
                ],
                max_length=255,
            ),
        ),
        migrations.RunPython(migrate_activity_to_program, reverse_code=do_nothing),
    ]
