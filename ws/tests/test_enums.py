import unittest

from ws import enums
from ws.utils.forms import all_choices


class ProgramTest(unittest.TestCase):
    def test_every_program_in_choices(self):
        """ At present, every program is a valid choice.

        We may choose to deprecate some program later. For now, enforce presence.
        """
        self.assertCountEqual(
            all_choices(enums.Program.choices()),
            [program.value for program in enums.Program],
        )

    def test_is_open(self):
        self.assertTrue(enums.Program.CIRCUS.is_open())
        self.assertTrue(enums.Program.SERVICE.is_open())
        self.assertTrue(enums.Program.NONE.is_open())

        self.assertFalse(enums.Program.WINTER_SCHOOL.is_open())

    def test_every_program_has_required_activity(self):
        """ Every program explicitly has a required activity. """
        for program in enums.Program:
            activity = program.required_activity()
            if activity is not None:
                self.assertTrue(isinstance(activity, enums.Activity))

    def test_required_activity(self):
        self.assertIsNone(enums.Program.CIRCUS.required_activity())
        self.assertIsNone(enums.Program.SERVICE.required_activity())
        self.assertIsNone(enums.Program.NONE.required_activity())

        # Two programs require WS ratings
        self.assertEqual(
            enums.Program.WINTER_SCHOOL.required_activity(),
            enums.Activity.WINTER_SCHOOL,
        )
        self.assertEqual(
            enums.Program.WINTER_NON_IAP.required_activity(),
            enums.Activity.WINTER_SCHOOL,
        )

        # Two programs require climbing ratings
        self.assertEqual(
            enums.Program.CLIMBING.required_activity(), enums.Activity.CLIMBING
        )
        self.assertEqual(
            enums.Program.MITOC_ROCK_PROGRAM.required_activity(),
            enums.Activity.CLIMBING,
        )


class TripTypeTest(unittest.TestCase):
    def test_every_program_in_choices(self):
        """ Every trip type is a valid choice. """
        self.assertCountEqual(
            all_choices(enums.TripType.choices()),
            [trip_type.value for trip_type in enums.TripType],
        )


class ActivityTest(unittest.TestCase):
    def test_every_activity_has_label(self):
        for activity in enums.Activity:
            self.assertTrue(activity.label)

    def test_is_winter_school(self):
        self.assertFalse(enums.Activity.CLIMBING.is_winter_school())
        self.assertTrue(enums.Activity.WINTER_SCHOOL.is_winter_school())
