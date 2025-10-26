from django.test import SimpleTestCase

from ws import enums, icons
from ws.tests import factories


class FontAwesomeIconTest(SimpleTestCase):
    def test_primary_program(self) -> None:
        """Some trip programs always use the same icon."""
        mrp_trip = factories.TripFactory.build(
            trip_type=enums.TripType.TRAD_CLIMBING.value,
            program=enums.Program.SCHOOL_OF_ROCK.value,
        )
        self.assertEqual(icons.fa_icon_for_trip(mrp_trip), "school")

        service_trip = factories.TripFactory.build(
            trip_type=enums.TripType.HIKING.value, program=enums.Program.SERVICE.value
        )
        self.assertEqual(icons.fa_icon_for_trip(service_trip), "hands-helping")

    def test_special_trip_types(self) -> None:
        """Most trip types have their own custom icon."""
        ice_trip = factories.TripFactory.build(
            trip_type=enums.TripType.ICE_CLIMBING.value,
            program=enums.Program.WINTER_SCHOOL.value,
        )
        self.assertEqual(icons.fa_icon_for_trip(ice_trip), "icicles")

        ultimate_trip = factories.TripFactory.build(
            name="Ultimate Pickup",
            trip_type=enums.TripType.ULTIMATE.value,
            program=enums.Program.NONE.value,
        )
        self.assertEqual(icons.fa_icon_for_trip(ultimate_trip), "compact-disc")

    def test_fall_back_on_program(self) -> None:
        """When lacking an icon for the trip type, we can fall back on program."""
        circus_trip = factories.TripFactory.build(
            trip_type=enums.TripType.NONE.value, program=enums.Program.CIRCUS.value
        )
        self.assertEqual(icons.fa_icon_for_trip(circus_trip), "users")

    def test_no_known_icon(self) -> None:
        """We don't always have an icon for the program/trip type combo."""
        other_trip = factories.TripFactory.build(
            trip_type=enums.TripType.OTHER.value, program=enums.Program.NONE.value
        )

        self.assertEqual(icons.fa_icon_for_trip(other_trip), "")

    def test_every_program_has_an_icon(self) -> None:
        """Each specific program has a corresponding icon."""
        # Specifically, we enumerate each program in the mapping
        self.assertCountEqual(enums.Program, icons.ICON_BY_PROGRAM)

        # Test the public interface, though
        for program in enums.Program:
            trip = factories.TripFactory.build(
                trip_type=enums.TripType.NONE.value, program=program.value
            )

            icon = icons.fa_icon_for_trip(trip)
            if trip.program_enum == enums.Program.NONE:
                self.assertEqual(icon, "")
            else:
                self.assertTrue(icon)


class TripIconTest(SimpleTestCase):
    def test_no_icon(self) -> None:
        """Without sufficient information, no icon can be rendered."""
        misc_trip = factories.TripFactory.build(
            trip_type=enums.TripType.OTHER.value, program=enums.Program.NONE.value
        )
        self.assertEqual(icons.for_trip(misc_trip), "")

    def test_regular_icon(self) -> None:
        """Some icons will use FontAwesome 'regular' over solid."""
        climbing_trip = factories.TripFactory.build(
            trip_type=enums.TripType.GYM_CLIMBING.value,
            program=enums.Program.CLIMBING.value,
        )
        self.assertEqual(
            icons.for_trip(climbing_trip),
            '<i class="far fa-fw fa-hand-rock" title="Gym climbing"></i>',
        )

    def test_no_trip_type(self) -> None:
        """For trips without a trip_type, we use program."""
        circus_trip = factories.TripFactory.build(
            trip_type=enums.TripType.NONE.value, program=enums.Program.CIRCUS.value
        )
        self.assertEqual(
            icons.for_trip(circus_trip),
            '<i class="fa fa-fw fa-users" title="Circus"></i>',
        )

        cabin_trip = factories.TripFactory.build(
            trip_type=enums.TripType.OTHER.value, program=enums.Program.CABIN.value
        )
        self.assertEqual(
            icons.for_trip(cabin_trip), '<i class="fa fa-fw fa-home" title="Cabin"></i>'
        )

    def test_trip_type(self) -> None:
        skating_trip = factories.TripFactory.build(
            trip_type=enums.TripType.ICE_SKATING.value,
            program=enums.Program.WINTER_SCHOOL.value,
        )
        self.assertEqual(
            icons.for_trip(skating_trip),
            '<i class="fa fa-fw fa-skating" title="Ice skating"></i>',
        )
