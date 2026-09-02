from django.contrib.auth.models import Group
from django.http import HttpResponseRedirect
from django.test import TestCase

from ws import enums, models
from ws.tests import factories


class RunTripLotteryViewTest(TestCase):
    def setUp(self) -> None:
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)
        super().setUp()

    def test_must_be_a_leader_on_trip(self) -> None:
        # It's not sufficient to be a leader, you must be leading the trip!
        factories.LeaderRatingFactory.create(participant=self.participant)
        trip = factories.TripFactory.create(algorithm="lottery")
        resp = self.client.post(f"/trips/{trip.pk}/admin/lottery/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Must be a leader", resp.content)

        self.assertEqual(trip.algorithm, "lottery")

    def _expect_lottery_to_run(self, trip: models.Trip) -> None:
        self.assertEqual(trip.algorithm, "lottery")
        resp = self.client.post(f"/trips/{trip.pk}/admin/lottery/")
        self.assertEqual(resp.status_code, 302)
        assert isinstance(resp, HttpResponseRedirect)
        self.assertEqual(resp.url, f"/trips/{trip.pk}/")
        trip.refresh_from_db()
        self.assertEqual(trip.algorithm, "fcfs")

    def test_cannot_run_on_a_ws_trip(self) -> None:
        trip = factories.TripFactory.create(
            algorithm="lottery",
            creator=self.participant,
            program=enums.Program.WINTER_SCHOOL.value,
        )
        resp = self.client.post(f"/trips/{trip.pk}/admin/lottery/")
        self.assertEqual(resp.status_code, 302)
        assert isinstance(resp, HttpResponseRedirect)
        view_trip_resp = self.client.get(resp.url)
        self.assertIn(
            b"Winter School trips run as part of a multi-trip lottery",
            view_trip_resp.content,
        )

        trip.refresh_from_db()
        self.assertEqual(trip.algorithm, "lottery")

    def test_run_lottery_as_creator(self) -> None:
        # You need not even have a leader rating, the creator can run it!
        trip = factories.TripFactory.create(
            algorithm="lottery",
            creator=self.participant,
            program=enums.Program.WINTER_NON_IAP.value,
        )
        self._expect_lottery_to_run(trip)

    def test_run_lottery_as_chair(self) -> None:
        Group.objects.get(name="hiking_chair").user_set.set([self.participant.user])
        trip = factories.TripFactory.create(
            algorithm="lottery", program=enums.Program.HIKING.value
        )
        self._expect_lottery_to_run(trip)

    def test_run_lottery_as_admin(self) -> None:
        self.participant.user.is_superuser = True
        self.participant.user.save()
        trip = factories.TripFactory.create(
            algorithm="lottery", program=enums.Program.CLIMBING.value
        )
        self._expect_lottery_to_run(trip)
