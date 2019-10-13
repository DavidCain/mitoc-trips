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


class TripTypeTest(unittest.TestCase):
    def test_every_program_in_choices(self):
        """ Every trip type is a valid choice. """
        self.assertCountEqual(
            all_choices(enums.TripType.choices()),
            [trip_type.value for trip_type in enums.TripType],
        )
