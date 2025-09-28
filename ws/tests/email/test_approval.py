from datetime import date

from django.test import TestCase
from freezegun import freeze_time

from ws import enums
from ws.email import approval
from ws.tests import factories


class ReminderEmailTest(TestCase):
    def test_no_trips(self) -> None:
        self.assertFalse(approval.at_least_one_trip_merits_reminder_email([]))

    def test_trip_without_required_activity(self) -> None:
        circus_trip = factories.TripFactory.create(program=enums.Program.CIRCUS.value)
        self.assertFalse(
            approval.at_least_one_trip_merits_reminder_email([circus_trip])
        )

    def test_past_trips_ignored(self) -> None:
        """Even if never approved, we missed the window to approve them."""
        trip = factories.TripFactory.create(trip_date=date(2025, 12, 1))

        # Same day it'd be remindable!
        with freeze_time("2025-12-01 23:59-05:00"):
            self.assertEqual(
                approval.at_least_one_trip_merits_reminder_email([trip]),
                [
                    f"Trip #{trip.pk} starts very soon (on 2025-12-01) but has no approval!"
                ],
            )
        # Next day though? Window is gone.
        with freeze_time("2025-12-02 00:10-05:00"):
            self.assertFalse(approval.at_least_one_trip_merits_reminder_email([trip]))

    def test_reminded_too_recently(self) -> None:
        """Ensure we have a very simple backstop against spam.

        Specifically, if we queue a ton of Celery tasks to send reminders, we *must*
        not send tons of emails. This is an idempotency check, basically.
        """
        # Doesn't matter when the trip date is! (Can even be in the past)
        # Fail super early if we've queued up too many reminder emails.
        trip = factories.TripFactory.create(program=enums.Program.CLIMBING)

        with freeze_time("2025-11-25 12:00 UTC"):
            factories.ChairApprovalReminderFactory.create(
                trip=trip,
                activity=trip.required_activity_enum().value,
                had_trip_info=False,
            )
        with freeze_time("2025-11-25 12:45 UTC"), self.assertLogs(level="ERROR") as log:
            self.assertFalse(approval.at_least_one_trip_merits_reminder_email([trip]))
        self.assertEqual(len(log.records), 1)
        self.assertEqual(
            log.records[0].message,
            "Trying to send another reminder at 2025-11-25 07:45:00-05:00, less than an hour since last reminder email at 2025-11-25 12:00:00+00:00",
        )

        # We can, however, notify *other* activity chairs!
        with freeze_time("2025-11-25 12:45 UTC"):
            trip = factories.TripFactory.create(
                program=enums.Program.HIKING.value,
                trip_date=date(2025, 11, 26),
            )
            self.assertTrue(approval.at_least_one_trip_merits_reminder_email([trip]))

    def test_reminder_already_sent_before_itinerary(self) -> None:
        # This trip has no trip info, but we already asked chairs to review it.
        trip = factories.TripFactory.create(info=None, trip_date=date(2025, 12, 1))
        factories.ChairApprovalReminderFactory.create(
            trip=trip,
            activity=trip.required_activity_enum().value,
            had_trip_info=False,
        )
        with freeze_time("2025-11-25 12:00 UTC"):
            self.assertFalse(trip.info_editable)  # Still can't be edited!
            self.assertFalse(approval.at_least_one_trip_merits_reminder_email([trip]))

    def test_reminder_sent_but_now_itinerary_is_completed(self) -> None:
        # This trip has no trip info, *and* we'd asked chairs to review.
        trip = factories.TripFactory.create(info=None, trip_date=date(2025, 11, 1))
        factories.ChairApprovalReminderFactory.create(
            trip=trip,
            activity=trip.activity,
            had_trip_info=False,
        )

        # Trip info is still not completed, so don't remind again
        with freeze_time("2025-10-25 12:00 UTC"):
            self.assertFalse(approval.at_least_one_trip_merits_reminder_email([trip]))

        # Closer to the trip date, itineraries are available
        with freeze_time("2025-10-30T19:00-05:00"):
            self.assertTrue(trip.info_editable)

            # Itinerary is *available*, but hasn't been filled out. Reminder is pointless!
            self.assertFalse(approval.at_least_one_trip_merits_reminder_email([trip]))

            # Once filled out, *now* we can remind chairs (there's new info to review!)
            factories.TripInfoFactory.create(trip=trip)
            trip.refresh_from_db()
            self.assertFalse(approval.at_least_one_trip_merits_reminder_email([trip]))

    def test_trip_leaves_tomorrow(self) -> None:
        trip = factories.TripFactory.create(info=None, trip_date=date(2025, 11, 1))
        factories.ChairApprovalReminderFactory.create(
            trip=trip,
            activity=trip.activity,
            had_trip_info=False,
        )
        # Even though we've sent a reminder *and* it still lacks itinerary...
        with freeze_time("2025-10-31T19:00-05:00"):
            self.assertTrue(approval.at_least_one_trip_merits_reminder_email([trip]))

    def test_trip_changed_activity_type(self) -> None:
        trip = factories.TripFactory.create(
            trip_date=date(2025, 11, 1), program=enums.Program.CLIMBING.value
        )
        factories.TripInfoFactory.create(trip=trip)
        with freeze_time("2025-10-30T19:00-05:00"):
            factories.ChairApprovalReminderFactory.create(
                trip=trip,
                # Pretend it was approved for a different activity type entirely!
                activity=enums.Activity.HIKING.value,
                had_trip_info=True,
            )
            self.assertEqual(
                approval.at_least_one_trip_merits_reminder_email([trip]),
                [
                    f"Trip #{trip.id} could complete an itinerary, "
                    "has done so, and chairs have not been emailed about the trip yet."
                ],
            )

    def test_only_one_trip_needs_reminding(self) -> None:
        with freeze_time("2025-10-30T19:00-05:00"):
            past_trip = factories.TripFactory.create(trip_date=date(2024, 3, 4))

            trip_approved = factories.TripFactory.create(chair_approved=True)
            factories.ChairApprovalFactory.create(
                trip=trip_approved, trip_edit_revision=trip_approved.edit_revision
            )
            itinerary_not_available = factories.TripFactory.create(
                trip_date=date(2026, 4, 5)
            )

            trips = [past_trip, trip_approved, itinerary_not_available]
            # self.assertFalse(approval.at_least_one_trip_merits_reminder_email(trips))

            # The addition of a single trip that needs approval changes it!
            new_trip = factories.TripFactory.create(
                info=None, trip_date=date(2025, 11, 1), chair_approved=False
            )
            self.assertTrue(new_trip.info_editable)
            self.assertTrue(
                approval.at_least_one_trip_merits_reminder_email([*trips, new_trip])
            )
