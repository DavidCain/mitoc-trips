from datetime import date, datetime
from unittest import mock
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core import mail
from django.test import TestCase
from freezegun import freeze_time
from mitoc_const import affiliations

from ws import enums, models, tasks
from ws.email import approval, renew
from ws.tests import factories


class TaskTests(TestCase):
    @staticmethod
    @patch("ws.utils.geardb.update_affiliation")
    def test_update_participant_affiliation(update_affiliation):
        participant = factories.ParticipantFactory.create(
            affiliation=affiliations.NON_AFFILIATE.CODE
        )
        tasks.update_participant_affiliation(participant.pk)
        update_affiliation.assert_called_with(participant)

    @staticmethod
    @freeze_time("Fri, 25 Jan 2019 03:00:00 EST")
    @patch("ws.tasks.send_email_to_funds")
    def test_send_tomorrow_itineraries(send_email_to_funds):
        """Only trips taking place the next day have itineraries sent out."""
        _yesterday, _today, tomorrow, _two_days_from_now = (
            factories.TripFactory.create(
                trip_date=date(2019, 1, day), info=factories.TripInfoFactory.create()
            )
            for day in [24, 25, 26, 27]
        )

        tasks.send_sole_itineraries()

        # Emails are only sent for trips going out tomorrow
        send_email_to_funds.assert_called_once_with(tomorrow)

    @freeze_time("Fri, 25 Jan 2019 03:00:00 EST")
    def test_trips_without_itineraries_included(self):
        trips_with_itinerary = [
            factories.TripFactory.create(
                trip_date=date(2019, 1, 26), info=factories.TripInfoFactory.create()
            )
            for i in range(2)
        ]

        # Create one trip without an itinerary, on the same day
        no_itinerary_trip = factories.TripFactory.create(
            trip_date=date(2019, 1, 26), info=None
        )

        with patch("ws.tasks.send_email_to_funds") as send_email_to_funds:
            tasks.send_sole_itineraries()

        # Emails were sent for *both* trips
        self.assertCountEqual(
            [trip for (trip,), kwargs in send_email_to_funds.call_args_list],
            [*trips_with_itinerary, no_itinerary_trip],
        )


@freeze_time("2019-01-25 12:00:00 EST")
class RemindAllParticipantsToRenewTest(TestCase):
    @staticmethod
    def test_nobody_needs_reminding():
        for exp_date in [
            date(2019, 1, 1),  # In the past
            date(2019, 3, 5),  # Can't renew just yet
            None,  # Never paid dues
        ]:
            factories.ParticipantFactory.create(
                send_membership_reminder=True,
                membership__membership_expires=exp_date,
            )

        # Participants with no known dues payments (or just a waiver) are never reminded
        factories.ParticipantFactory.create(
            send_membership_reminder=True, membership=None
        )
        # Waiver expires soon, but we won't remind about that.
        factories.ParticipantFactory.create(
            send_membership_reminder=True,
            membership__waiver_expires=date(2019, 1, 28),
            membership__membership_expires=None,
        )

        # We remind participants exactly once (per membership)
        already_reminded = factories.ParticipantFactory.create(
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 1, 28),
        )
        factories.MembershipReminderFactory.create(
            participant=already_reminded,
            reminder_sent_at=datetime(2020, 12, 25, tzinfo=ZoneInfo("UTC")),
        )

        with patch.object(tasks.remind_lapsed_participant_to_renew, "delay") as email:
            tasks.remind_participants_to_renew()
        email.assert_not_called()

    @staticmethod
    def test_delays_participants_who_are_eligible():
        par = factories.ParticipantFactory.create(
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 2, 2),
        )
        with patch.object(tasks.remind_lapsed_participant_to_renew, "delay") as email:
            tasks.remind_participants_to_renew()
        email.assert_called_once_with(par.pk)

    @staticmethod
    def test_can_be_reminded_once_a_year():
        par = factories.ParticipantFactory.create(
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 2, 2),
        )
        # We reminded them once before, but it was for the previous year's membership
        factories.MembershipReminderFactory.create(
            participant=par,
            reminder_sent_at=datetime(2017, 12, 25, tzinfo=ZoneInfo("UTC")),
        )
        with patch.object(tasks.remind_lapsed_participant_to_renew, "delay") as email:
            tasks.remind_participants_to_renew()
        email.assert_called_once_with(par.pk)


@freeze_time("2019-01-25 12:00:00 EST")
class RemindIndividualParticipantsToRenewTest(TestCase):
    def test_first_reminder(self):
        par = factories.ParticipantFactory.create(
            name="Tim Beaver",
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 1, 27),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            tasks.remind_lapsed_participant_to_renew(par.pk)
        send.assert_called_once()

        reminder = models.MembershipReminder.objects.get()
        self.assertEqual(
            str(reminder), "Tim Beaver, last reminded at 2019-01-25T17:00+00:00"
        )
        self.assertEqual(reminder.participant, par)
        self.assertEqual(
            reminder.reminder_sent_at,
            datetime(2019, 1, 25, 17, 0, tzinfo=ZoneInfo("UTC")),
        )

    def test_second_annual_reminder(self):
        par = factories.ParticipantFactory.create(
            name="Tim Beaver",
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 1, 27),
        )
        # Last reminder was a little less than a year ago
        factories.MembershipReminderFactory.create(
            participant=par,
            reminder_sent_at=datetime(2018, 1, 28, tzinfo=ZoneInfo("UTC")),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            tasks.remind_lapsed_participant_to_renew(par.pk)
        send.assert_called_once()

        self.assertEqual(
            models.MembershipReminder.objects.filter(participant=par).count(), 2
        )
        last_reminder = models.MembershipReminder.objects.latest("reminder_sent_at")
        self.assertEqual(
            last_reminder.reminder_sent_at,
            datetime(2019, 1, 25, 17, 0, tzinfo=ZoneInfo("UTC")),
        )

    def test_idempotent(self):
        """If we try to notify the same participant twice, only one email sent."""
        par = factories.ParticipantFactory.create(
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 1, 27),
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send:
            tasks.remind_lapsed_participant_to_renew(par.pk)
        send.assert_called_once()
        self.assertEqual(
            models.MembershipReminder.objects.filter(participant=par).count(),
            1,
        )

        with mock.patch.object(mail.EmailMultiAlternatives, "send") as send2:
            with self.assertRaises(ValueError):
                tasks.remind_lapsed_participant_to_renew(par.pk)
        send2.assert_not_called()
        self.assertEqual(
            models.MembershipReminder.objects.filter(participant=par).count(),
            1,
        )

    def test_participant_has_opted_out(self):
        """We cover the possibility of a participant opting out after a reminder was scheduled."""
        par = factories.ParticipantFactory.create(
            send_membership_reminder=False,
            membership__membership_expires=date(2019, 1, 27),
        )

        with patch.object(renew, "send_email_reminding_to_renew") as email:
            tasks.remind_lapsed_participant_to_renew(par.pk)
        email.assert_not_called()
        self.assertFalse(models.MembershipReminder.objects.exists())

    def test_tried_to_remind_again_too_soon(self):
        par = factories.ParticipantFactory.create(
            send_membership_reminder=True,
            membership__membership_expires=date(2019, 1, 27),
        )
        factories.MembershipReminderFactory.create(
            participant=par,
            reminder_sent_at=datetime(2018, 4, 25, tzinfo=ZoneInfo("UTC")),
        )

        with patch.object(renew, "send_email_reminding_to_renew") as email:
            with self.assertRaises(ValueError) as cm:
                tasks.remind_lapsed_participant_to_renew(par.pk)
        self.assertIn("Mistakenly trying to notify", str(cm.exception))
        email.assert_not_called()
        only_reminder = models.MembershipReminder.objects.get(participant=par)
        self.assertEqual(
            only_reminder.reminder_sent_at,
            datetime(2018, 4, 25, tzinfo=ZoneInfo("UTC")),
        )

    def test_errors_actually_sending_mail_caught(self):
        par = factories.ParticipantFactory.create(
            send_membership_reminder=True,
            # We obviously won't remind somebody to renew a null membership
            membership=None,
        )

        with self.assertRaises(ValueError) as cm:
            tasks.remind_lapsed_participant_to_renew(par.pk)
        self.assertIn("no membership on file", str(cm.exception))

        # We don't record a successful reminder being sent.
        self.assertFalse(
            models.MembershipReminder.objects.filter(
                reminder_sent_at__isnull=False
            ).exists()
        )


class RunLotteryTest(TestCase):
    def setUp(self):
        # Create a trip to make sure the ID sequence is initialized.
        # Without this step, Postgres may raise an exception on `select currval()`
        # This is an okay assumption to make at test time:
        # `run_lottery()` should only be invoked after at least one trip is created.
        factories.TripFactory.create()

        super().setUp()

    def test_bogus_trip_pk(self):
        """Make sure that the task fails if passed an ID that was never a real trip."""
        # I sure hope `nextval()` never creates 32k trips in our test suite...
        with self.assertRaises(models.Trip.DoesNotExist):
            tasks.run_lottery(32_000)

    def test_zero_pk(self):
        """All our sequences start at 1; 0 is never a valid pk."""
        with self.assertRaises(models.Trip.DoesNotExist):
            tasks.run_lottery(0)

    def test_non_integer_trip_id(self):
        """Make sure that we raise *something* if given a non-integer ID.

        We do some integer comparisons of the given ID & `currval()`,
        and we don't want invalid IDs to be considered an ID of a
        since-deleted trip.

        This test is valuable because mypy type checking can easily
        be bypassed at runtime.
        """
        with self.assertRaises(ValueError):
            tasks.run_lottery("not-an-id")

    def test_trip_deleted(self):
        """We silently complete the task if the trip was deleted."""
        trip = factories.TripFactory.create()
        trip_id = trip.pk
        trip.delete()
        tasks.run_lottery(trip_id)

    def test_trip_not_the_most_recent_deleted(self):
        """Our `currval()` logic can handle trips which have PKs lower than the latest."""
        trip = factories.TripFactory.create()
        trip_id = trip.pk
        newer_trip = factories.TripFactory.create()
        self.assertGreater(newer_trip.pk, trip.pk)
        trip.delete()
        tasks.run_lottery(trip_id)

    def test_success(self):
        """Test the usual case: a real trip exists, needs a lottery run."""
        trip = factories.TripFactory.create(algorithm="lottery")
        tasks.run_lottery(trip.pk)
        trip.refresh_from_db()
        self.assertEqual(trip.algorithm, "fcfs")


class UnapprovedTripsReminderTest(TestCase):
    @freeze_time("2025-10-25 17:00-05:00")
    def test_no_reminders_necessary(self):
        factories.TripFactory.create(trip_date=date(2025, 10, 24))
        factories.TripFactory.create(program=enums.Program.NONE.value)
        factories.TripFactory.create(program=enums.Program.CIRCUS.value)
        approved = factories.TripFactory.create(
            trip_date=date(2025, 10, 26), chair_approved=True
        )
        # Not actually consulted at present, but let's favor a complete data model
        factories.ChairApprovalFactory.create(trip=approved)

        with patch.object(
            tasks.email_activity_chair_about_unapproved_trips, "delay"
        ) as email:
            tasks.email_all_activity_chairs_about_unapproved_trips()
        email.assert_not_called()

    @freeze_time("2025-10-25 17:00-05:00")
    def test_reminders_necessary(self) -> None:
        factories.TripFactory.create(
            program=enums.Program.CLIMBING.value, chair_approved=True
        )
        trip = factories.TripFactory.create(
            program=enums.Program.HIKING.value,
            trip_date=date(2025, 10, 26),
            chair_approved=False,
        )
        with patch.object(
            tasks.email_activity_chair_about_unapproved_trips, "delay"
        ) as email:
            tasks.email_all_activity_chairs_about_unapproved_trips()
        email.assert_called_once_with("hiking", [trip.id])

        with patch.object(approval, "notify_activity_chair") as send_email:
            tasks.email_activity_chair_about_unapproved_trips(
                enums.Activity.HIKING.value, [trip.id]
            )
        send_email.assert_called_once_with(
            enums.Activity.HIKING,
            [trip],
            [f"trip #{trip.pk} starts very soon (on 2025-10-26) but has no approval!"],
        )
