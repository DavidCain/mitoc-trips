from datetime import date, datetime

from freezegun import freeze_time

import ws.utils.dates as date_utils
from ws import enums
from ws.tests import TestCase, factories


@freeze_time("2019-01-15 12:25:00 EST")
class SignupsViewTest(TestCase):
    databases = {'geardb', 'auth_db', 'default'}

    def _signup(self, trip):
        return self.client.post('/trips/signup/', {'trip': trip.pk}, follow=False)

    def _active_member(self):
        par = factories.ParticipantFactory.create()
        self.assertTrue(par.membership_active)
        return par

    @staticmethod
    def _upcoming_trip(**kwargs):
        trip_kwargs = {
            'program': enums.Program.CLIMBING.value,
            'trip_date': date(2019, 1, 19),
            'signups_open_at': date_utils.localize(datetime(2019, 1, 14, 10, 0, 0)),
            **kwargs,
        }
        return factories.TripFactory.create(**trip_kwargs)

    def test_signup(self):
        """Posting to the signup flow creates a SignUp object!

        In this case:
        - signups are currently open
        - the participant is an active member
        """
        trip = self._upcoming_trip(algorithm='lottery')

        # The participant has an active membership that will last at least until the trip
        par = self._active_member()
        self.assertFalse(par.should_renew_for(trip))

        self.client.force_login(par.user)
        resp = self._signup(trip)

        # Sign up was successful, and we're redirected to the trip page!
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/trips/{trip.pk}/')

        # Participant was not placed on the trip, since it's a lottery!
        signup = trip.signup_set.get(participant=par)
        self.assertFalse(signup.on_trip)

    def test_wimp_cannot_attend(self):
        """For safety reasons, the WIMP should never be on the trip."""
        par = self._active_member()
        trip = self._upcoming_trip(wimp=par)

        self.client.force_login(par.user)
        resp = self._signup(trip)

        self.assertEqual(
            resp.context['form'].errors,
            {'__all__': ["Cannot attend a trip as its WIMP"]},
        )

    def test_leader_cannot_signup(self):
        """Leaders cannot sign up as participants."""
        par = self._active_member()
        trip = self._upcoming_trip()
        trip.leaders.add(par)

        self.client.force_login(par.user)
        resp = self._signup(trip)

        self.assertEqual(
            resp.context['form'].errors, {'__all__': ["Already a leader on this trip!"]}
        )

    def test_already_on_trip(self):
        """If already signed up, signing up again does not create a duplicate."""
        par = self._active_member()
        trip = self._upcoming_trip()
        factories.SignUpFactory.create(participant=par, trip=trip, on_trip=False)

        self.client.force_login(par.user)
        resp = self._signup(trip)

        self.assertEqual(
            resp.context['form'].errors,
            {'__all__': ["Already signed up for this trip!"]},
        )

        # The original signup remains in place, unchanged and not duplicated.
        signup = trip.signup_set.get(participant=par)
        self.assertFalse(signup.on_trip)

    def test_trip_not_open(self):
        """Cannot sign up for a trip that's not open!"""
        not_yet_open_trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            signups_open_at=date_utils.localize(datetime(2019, 3, 20, 10, 0, 0)),
        )

        # The participant has an active membership that will last at least until the trip
        par = self._active_member()
        self.assertFalse(par.should_renew_for(not_yet_open_trip))

        # However, because the trip is in the future, they cannot sign up!
        self.client.force_login(par.user)
        resp = self._signup(not_yet_open_trip)
        form = resp.context['form']
        self.assertEqual(form.errors, {'__all__': ["Signups aren't open!"]})

        # Participant was not placed on the trip.
        self.assertFalse(not_yet_open_trip.signup_set.filter(participant=par).exists())

    def test_membership_required(self):
        """Only active members are allowed on the trip."""
        par = factories.ParticipantFactory.create(membership=None)
        trip = self._upcoming_trip(membership_required=True)
        self.assertTrue(par.should_renew_for(trip))

        self.client.force_login(par.user)
        resp = self._signup(trip)
        form = resp.context['form']
        self.assertEqual(
            form.errors,
            {
                '__all__': [
                    "An active membership is required",
                    "A current waiver is required",
                ]
            },
        )

        # Participant was not placed on the trip.
        self.assertFalse(trip.signup_set.filter(participant=par).exists())

    def test_active_waiver_required(self):
        """Only active members are allowed on the trip."""
        par = factories.ParticipantFactory.create(
            membership=factories.MembershipFactory.create(
                membership_expires=date(2020, 1, 5), waiver_expires=None
            )
        )
        mini_trip = self._upcoming_trip(membership_required=False)

        # Membership is not required for the mini trip, but a waiver is!
        self.assertFalse(par.should_renew_for(mini_trip))

        self.client.force_login(par.user)
        resp = self._signup(mini_trip)
        form = resp.context['form']
        self.assertEqual(form.errors, {'__all__': ["A current waiver is required"]})

        # Participant was not placed on the trip.
        self.assertFalse(mini_trip.signup_set.filter(participant=par).exists())

    def test_missed_lectures(self):
        # Presence of an existing WS trip is the clue that WS has started.
        factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, trip_date=date(2019, 1, 12)
        )
        self.assertTrue(date_utils.ws_lectures_complete())

        ws_trip = self._upcoming_trip(program=enums.Program.WINTER_SCHOOL.value)

        # This participant is not a member! (that's important -- it shapes error messages)
        par = factories.ParticipantFactory.create(membership=None)

        self.assertFalse(par.attended_lectures(2019))
        self.assertTrue(par.missed_lectures_for(ws_trip))

        self.client.force_login(par.user)
        resp = self._signup(ws_trip)
        form = resp.context['form']

        # Normally, we would prompt the participant to pay dues & sign a waiver.
        # However, since they might pay dues, then be frustrated that they cannot attend, we don't.
        self.assertEqual(
            form.errors, {'__all__': ["Must have attended mandatory safety lectures"]}
        )
