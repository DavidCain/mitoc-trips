from datetime import date
from unittest import mock

from bs4 import BeautifulSoup
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase
from freezegun import freeze_time

from ws import enums, models
from ws.email import approval
from ws.tests import factories, strip_whitespace


class ReminderEmailTest(TestCase):
    def test_no_trips(self) -> None:
        self.assertFalse(approval.reasons_to_remind_activity_chairs([]))

    def test_trip_without_required_activity(self) -> None:
        circus_trip = factories.TripFactory.create(program=enums.Program.CIRCUS.value)
        self.assertFalse(approval.reasons_to_remind_activity_chairs([circus_trip]))

    def test_past_trips_ignored(self) -> None:
        """Even if never approved, we missed the window to approve them."""
        trip = factories.TripFactory.create(trip_date=date(2025, 12, 1))

        # Same day it'd be remindable!
        with freeze_time("2025-12-01 23:59-05:00"):
            self.assertEqual(
                approval.reasons_to_remind_activity_chairs([trip]),
                [
                    f"trip #{trip.pk} starts very soon (on 2025-12-01) but has no approval!"
                ],
            )
        # Next day though? Window is gone.
        with freeze_time("2025-12-02 00:10-05:00"):
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))

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
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))
        self.assertEqual(len(log.records), 1)
        self.assertEqual(
            log.records[0].message,
            "Trying to send another reminder for climbing trips at 2025-11-25 07:45:00-05:00, less than an hour since last reminder email at 2025-11-25 12:00:00+00:00",
        )

        # We can, however, notify *other* activity chairs!
        with freeze_time("2025-11-25 12:45 UTC"):
            trip = factories.TripFactory.create(
                program=enums.Program.HIKING.value,
                trip_date=date(2025, 11, 26),
            )
            reasons = approval.reasons_to_remind_activity_chairs([trip])
        self.assertEqual(
            reasons,
            [f"trip #{trip.pk} starts very soon (on 2025-11-26) but has no approval!"],
        )

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
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))

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
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))

        # Closer to the trip date, itineraries are available
        with freeze_time("2025-10-30T19:00-05:00"):
            self.assertTrue(trip.info_editable)

            # Itinerary is *available*, but hasn't been filled out. Reminder is pointless!
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))

            # Once filled out, *now* we can remind chairs (there's new info to review!)
            trip.info = factories.TripInfoFactory.create()
            trip.save()
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))

    def test_trip_leaves_tomorrow(self) -> None:
        trip = factories.TripFactory.create(info=None, trip_date=date(2025, 11, 1))
        with freeze_time("2025-10-30T19:00-05:00"):
            factories.ChairApprovalReminderFactory.create(
                trip=trip,
                activity=trip.activity,
                had_trip_info=False,
            )
        # Even though we've sent a reminder *and* it still lacks itinerary...
        with freeze_time("2025-10-31T19:00-05:00"):
            reasons = approval.reasons_to_remind_activity_chairs([trip])
        self.assertEqual(
            reasons,
            [f"trip #{trip.pk} starts very soon (on 2025-11-01) but has no approval!"],
        )

    def test_trip_changed_activity_type(self) -> None:
        trip = factories.TripFactory.create(
            trip_date=date(2025, 11, 1),
            program=enums.Program.CLIMBING.value,
            info=factories.TripInfoFactory.create(),
        )
        with freeze_time("2025-10-30T19:00-05:00"):
            factories.ChairApprovalReminderFactory.create(
                trip=trip,
                # Pretend it was approved for a different activity type entirely!
                activity=enums.Activity.HIKING.value,
                had_trip_info=True,
            )
            self.assertIs(trip.info_editable, True)
            reasons = approval.reasons_to_remind_activity_chairs([trip])
        self.assertEqual(
            reasons,
            [f"trip #{trip.id} changed activities (a reminder was sent for Hiking)"],
        )

    def test_only_one_trip_needs_reminding(self) -> None:
        with freeze_time("2025-10-30T19:00-05:00"):
            past_trip = factories.TripFactory.create(trip_date=date(2024, 3, 4))

            trip_approved = factories.TripFactory.create(chair_approved=True)
            factories.ChairApprovalFactory.create(trip=trip_approved)
            itinerary_not_available = factories.TripFactory.create(
                trip_date=date(2026, 4, 5)
            )

            trips = [past_trip, trip_approved, itinerary_not_available]
            self.assertFalse(approval.reasons_to_remind_activity_chairs(trips))

            # The addition of a single trip that needs approval changes it!
            new_trip = factories.TripFactory.create(
                info=None, trip_date=date(2025, 11, 1), chair_approved=False
            )
            self.assertTrue(new_trip.info_editable)
            reasons = approval.reasons_to_remind_activity_chairs([*trips, new_trip])
            self.assertEqual(
                reasons,
                [f"trip #{new_trip.pk} has not been sent to activity chairs"],
            )

    def test_itinerary_since_completed(self) -> None:
        with freeze_time("2025-10-30T17:00-05:00"):
            trip = factories.TripFactory.create(
                trip_date=date(2025, 11, 1),
                chair_approved=False,
                program=enums.Program.CLIMBING.value,
            )
            factories.ChairApprovalReminderFactory.create(
                trip=trip,
                had_trip_info=False,
                activity=enums.Activity.CLIMBING.value,
            )

        with freeze_time("2025-10-30T19:00-05:00"):
            self.assertTrue(trip.info_editable)

            # Enough time has passed, but we won't notify again because nothing's changed.
            self.assertFalse(approval.reasons_to_remind_activity_chairs([trip]))

            # But once an itinerary is completed, we can notify again!
            trip.info = factories.TripInfoFactory.create()
            trip.save()
            reasons = approval.reasons_to_remind_activity_chairs([trip])
            self.assertEqual(
                reasons,
                [f"trip #{trip.pk} now has an itinerary"],
            )

    @freeze_time("2025-11-06 12:45 -05:00")
    def test_notify_activity_chair(self) -> None:
        trip_1 = factories.TripFactory.create(
            name="Whitney G", trip_date=date(2025, 11, 7)
        )
        trip_2 = factories.TripFactory.create(
            name="Moby G", trip_date=date(2025, 11, 16)
        )
        with mock.patch.object(EmailMultiAlternatives, "send") as send:
            msg = approval.notify_activity_chair(
                activity_enum=enums.Activity.CLIMBING,
                trips=[trip_1, trip_2],
                reasons_to_send=[
                    f"trip #{trip_1.pk} has not been sent to activity chairs",
                    f"trip #{trip_2.pk} now has an itinerary",
                ],
            )
        reminder = models.ChairApprovalReminder.objects.get(trip=trip_1)
        self.assertEqual(reminder.activity, enums.Activity.CLIMBING.value)
        self.assertIs(reminder.had_trip_info, False)
        send.assert_called_once()

        expected_msg = "\n".join(
            [
                "2 climbing trips need activity chair approval as of Thursday, November 6",
                "https://mitoc-trips.mit.edu/climbing/trips/",
                "",
                "- Whitney G (Fri, Nov 7)",
                "- Moby G (Sun, Nov 16)",
                "",
                "You received this email because you are an activity chair.",
                "The only way to unsubscribe to these automated messages is to remove",
                "yourself from the activity chair mailing list. If you have questions,",
                "contact mitoc-webmaster@mit.edu or mitoc-owner@mit.edu.",
                "",
                "We sent this reminder because:",
                f"- trip #{trip_1.pk} has not been sent to activity chairs",
                f"- trip #{trip_2.pk} now has an itinerary",
            ]
        )
        self.assertIn(expected_msg, msg.body)

        self.assertEqual(len(msg.alternatives), 1)
        html, attachment_type = msg.alternatives[0]
        self.assertEqual(attachment_type, "text/html")
        assert isinstance(html, str)
        soup = BeautifulSoup(html, "html.parser")
        assert soup.title is not None
        self.assertEqual(
            soup.title.text,
            "Climbing trips need activity chair approval as of Thursday, November 6",
        )

        trip_link = soup.find(
            href=f"https://mitoc-trips.mit.edu/climbing/trips/{trip_1.pk}/"
        )
        assert trip_link is not None
        self.assertEqual(trip_link.text, "Whitney G")

        moby_g = soup.find(string="Moby G")
        assert moby_g is not None
        first_label = moby_g.find_next("li")
        assert first_label is not None
        self.assertEqual(
            strip_whitespace(first_label.text),
            "Itinerary: Will become available on Thursday, Nov 13th",
        )

        footer = soup.find(class_="footer")
        assert footer is not None
        reasons = (
            "We sent this reminder because "
            f"trip #{trip_1.pk} has not been sent to activity chairs, "
            f"trip #{trip_2.pk} now has an itinerary"
        )
        self.assertIn(reasons, footer.text)
