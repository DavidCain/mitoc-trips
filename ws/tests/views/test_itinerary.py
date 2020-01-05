from datetime import date

from bs4 import BeautifulSoup
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums
from ws.tests import TestCase, factories


@freeze_time("2019-02-15 12:25:00 EST")
class ChairTripViewTest(TestCase):
    def setUp(self):
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    @staticmethod
    def _make_climbing_trip(chair_approved=False, **kwargs):
        return factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            activity=enums.Activity.CLIMBING.value,
            chair_approved=chair_approved,
            **kwargs,
        )

    def test_must_be_chair(self):
        trip = self._make_climbing_trip()
        response = self.client.get(f'/climbing/trips/{trip.pk}/')
        self.assertEqual(response.status_code, 403)

    def test_view_old_unapproved_trip(self):
        trip = self._make_climbing_trip(
            chair_approved=False, trip_date=date(2018, 3, 4)
        )

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        response = self.client.get(f'/climbing/trips/{trip.pk}/')
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')

        # Even though the trip is old, we can still approve it.
        form = soup.find('form', action='.')
        self.assertTrue(form.find('button', text='Approve'))

        # There are no other unapproved trips to navigate between.
        self.assertIsNone(response.context['prev_trip'])
        self.assertIsNone(response.context['next_trip'])

        # Submitting the form approves the trip!
        # Because it's the last one, it goes back to the main listing.
        approve_resp = self.client.post(f'/climbing/trips/{trip.pk}/')
        self.assertEqual(approve_resp.status_code, 302)
        self.assertEqual(approve_resp.url, '/climbing/trips/')

    def test_view_old_approved_trip(self):
        trip = self._make_climbing_trip(chair_approved=True, trip_date=date(2018, 3, 4))
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        response = self.client.get(f'/climbing/trips/{trip.pk}/')
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, 'html.parser')

        # There's no approval form, just an indicator that it's approved
        self.assertFalse(soup.find('form', action='.'))
        self.assertTrue(soup.find('button', text='Approved!'))

    def test_upcoming_trips(self):
        four = self._make_climbing_trip(trip_date=date(2019, 3, 4), name='four')
        two = self._make_climbing_trip(trip_date=date(2019, 3, 2), name='two')
        three = self._make_climbing_trip(trip_date=date(2019, 3, 3), name='three')
        one = self._make_climbing_trip(trip_date=date(2019, 3, 1), name='one')

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        # "Next" and "previous" are in reverse chronological order!
        response = self.client.get(f'/climbing/trips/{two.pk}/')
        self.assertEqual(response.context['prev_trip'], three)
        self.assertEqual(response.context['next_trip'], one)

        # Because we have a next trip, the button to approve it links to "& next"
        soup = BeautifulSoup(response.content, 'html.parser')
        form = soup.find('form', action='.')
        self.assertTrue(form.find('button', text='Approve & Next'))

        # Also, next and previous only navigate between unapproved trips
        three.chair_approved = True
        three.save()
        response = self.client.get(f'/climbing/trips/{two.pk}/')
        self.assertEqual(response.context['prev_trip'], four)
        self.assertEqual(response.context['next_trip'], one)

        # Finally, approving a trip brings us straight to the page for the next.
        approve_resp = self.client.post(f'/climbing/trips/{two.pk}/')
        self.assertEqual(approve_resp.status_code, 302)
        self.assertEqual(approve_resp.url, f'/climbing/trips/{one.pk}/')

    def test_no_navigation_between_old_trips(self):
        trip = self._make_climbing_trip(
            chair_approved=False, trip_date=date(2018, 3, 4)
        )
        self._make_climbing_trip(chair_approved=False, trip_date=date(2018, 3, 3))
        self._make_climbing_trip(chair_approved=False, trip_date=date(2018, 3, 5))

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        response = self.client.get(f'/climbing/trips/{trip.pk}/')

        # We don't prompt the chair to approve other old trips.
        self.assertIsNone(response.context['prev_trip'])
        self.assertIsNone(response.context['next_trip'])
