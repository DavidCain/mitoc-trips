from contextlib import contextmanager
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

import responses
from bs4 import BeautifulSoup
from django.contrib import messages
from django.test import TestCase
from freezegun import freeze_time

import ws.utils.dates as date_utils
from ws import enums, models
from ws.tests import factories, strip_whitespace


@freeze_time("2019-01-15 12:25:00 EST")
class SignupsViewTest(TestCase):
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
            'signups_open_at': datetime(
                2019, 1, 14, 10, 0, 0, tzinfo=ZoneInfo("America/New_York")
            ),
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
        # The user's membership & waiver will be current enough, no need to update.
        with responses.RequestsMock():  # No API calls expected
            resp = self._signup(trip)

        # Sign up was successful, and we're redirected to the trip page!
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/trips/{trip.pk}/')

        # Participant was not placed on the trip, since it's a lottery!
        signup = trip.signup_set.get(participant=par)
        self.assertFalse(signup.on_trip)

    def test_no_such_trip(self):
        self.client.force_login(self._active_member().user)
        resp = self.client.post('/trips/signup/', {'trip': -10}, follow=False)
        self.assertIn('trip', resp.context['form'].errors)

    def test_notes_required_if_on_trip(self):
        trip = self._upcoming_trip(notes='Can you drive?')
        self.client.force_login(self._active_member().user)
        resp = self._signup(trip)
        self.assertEqual(
            resp.context['form'].errors,
            {'notes': ['Please complete notes to sign up!']},
        )

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
            signups_open_at=datetime(
                2019, 3, 20, 10, 0, 0, tzinfo=ZoneInfo("America/New_York")
            ),
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

    @responses.activate
    def test_membership_required(self):
        """Only active members are allowed on the trip."""
        par = factories.ParticipantFactory.create(
            membership=None, email='par@example.com'
        )
        trip = self._upcoming_trip(membership_required=True)
        self.assertTrue(par.should_renew_for(trip))

        check_membership = responses.get(
            url='https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=par@example.com',
            json={
                "count": 0,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "email": "",
                        "alternate_emails": [],
                        "membership": {},
                        "waiver": {},
                    }
                ],
            },
        )

        self.client.force_login(par.user)
        resp = self._signup(trip)

        # Because the user had an out-of-date membership, we checked for the latest
        self.assertEqual(check_membership.call_count, 1)

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

    @responses.activate
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

        check_waiver = responses.get(
            url=f'https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email={par.email}',
            json={
                "count": 0,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "email": "",
                        "alternate_emails": [],
                        "membership": {
                            "membership_type": "NA",
                            "expires": "2023-05-05",
                        },
                        # No waiver!
                        "waiver": {},
                    }
                ],
            },
        )

        self.client.force_login(par.user)
        resp = self._signup(mini_trip)
        self.assertEqual(resp.status_code, 200)  # (Failure, but errors shown)

        # Because the user had an out-of-date waiver, we checked for the latest
        self.assertEqual(check_waiver.call_count, 1)

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


class PairedParticipantSignupTest(TestCase):
    def setUp(self):
        self.bert = factories.ParticipantFactory.create(name="Bert B")
        self.ernie = factories.ParticipantFactory.create(name="Ernie E")

        # Reciprocally pair them
        factories.LotteryInfoFactory.create(
            participant=self.bert, paired_with=self.ernie
        )
        factories.LotteryInfoFactory.create(
            participant=self.ernie, paired_with=self.bert
        )
        super().setUp()

    @staticmethod
    @contextmanager
    def _spy_on_message_success():
        patched = mock.patch.object(messages, 'success', wraps=messages.success)
        with patched as success:
            yield success

    def test_pairing_ignored_if_trip_ignores_it(self):
        trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            algorithm='lottery',
            honor_participant_pairing=False,
        )
        self.client.force_login(self.bert.user)
        with self._spy_on_message_success() as bert_success:
            self.client.post('/trips/signup/', {'trip': trip.pk})
        models.SignUp.objects.get(participant=self.bert, trip=trip, on_trip=False)
        bert_success.assert_called_once_with(mock.ANY, "Signed up!")

    def test_single_trip_reciprocal_pairing(self):
        trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            algorithm='lottery',
            honor_participant_pairing=True,
        )

        # Bert signs up first, is told that Ernie has not.
        self.client.force_login(self.bert.user)
        with self._spy_on_message_success() as bert_success:
            self.client.post('/trips/signup/', {'trip': trip.pk})
        models.SignUp.objects.get(participant=self.bert, trip=trip, on_trip=False)
        bert_success.assert_called_once_with(
            mock.ANY,  # (The request object)
            "Signed up! You're paired with Ernie E. "
            "If they do not sign up for this trip, the lottery will attempt to place you alone on this trip.",
        )

        # Ernie signs up next; they'll be paired together
        self.client.force_login(self.ernie.user)
        with self._spy_on_message_success() as ernie_success:
            self.client.post('/trips/signup/', {'trip': trip.pk})
        models.SignUp.objects.get(participant=self.ernie, trip=trip, on_trip=False)
        ernie_success.assert_called_once_with(
            mock.ANY,  # (The request object)
            "Signed up! You're paired with Bert B. "
            "The lottery will attempt to place you together.",
        )


class LeaderSignupViewTest(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)
        super().setUp()

    def test_trip_must_be_specified(self):
        """Ensure that we don't 500 on an odd edge case - no trip specified!

        This should really only be possible via direct API hits.
        Otherwise, all forms are rendered with a trip's primary key.
        """
        # Give a rating, so we don't get a 403
        factories.LeaderRatingFactory.create(
            participant=self.participant,
            activity=enums.Activity.CLIMBING.value,
        )

        resp = self.client.post('/trips/signup/leader/', {})
        self.assertEqual(
            resp.context['form'].errors, {'trip': ['This field is required.']}
        )

    def test_leader_with_rating_can_sign_up(self):
        trip = factories.TripFactory.create(
            allow_leader_signups=True,
            program=enums.Program.CLIMBING.value,
            notes='Favorite passive protection?',
        )
        self.participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=self.participant,
                activity=enums.Activity.CLIMBING.value,
            )
        )

        # After successful signup, participant is routed back to the trip
        resp = self.client.post(
            '/trips/signup/leader/', {'trip': trip.pk, 'notes': 'Tricams'}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/trips/{trip.pk}/')

        # Signup object is written & leader is also added to the trip
        models.LeaderSignUp.objects.get(
            trip=trip, participant=self.participant, notes='Tricams'
        )
        self.assertIn(self.participant, trip.leaders.all())

    def test_must_be_leader(self):
        """Obviously, only leaders may sign up as a leader."""
        trip = factories.TripFactory.create(
            allow_leader_signups=True, program=enums.Program.NONE.value
        )
        self.assertFalse(set(self.participant.reasons_cannot_attend(trip)))

        resp = self.client.post('/trips/signup/leader/', {'trip': trip.pk})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(models.LeaderSignUp.objects.filter(trip=trip).exists())

    def test_must_be_able_to_lead_for_trip_program(self):
        """It's not sufficient to just be a leader, you must be rated accordingly."""
        trip = factories.TripFactory.create(
            allow_leader_signups=True, program=enums.Program.CLIMBING.value, notes=''
        )
        self.participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=self.participant,
                activity=enums.Activity.HIKING.value,
            )
        )

        resp = self.client.post('/trips/signup/leader/', {'trip': trip.pk})
        self.assertEqual(
            resp.context['form'].errors, {'__all__': ["Can't lead Climbing trips!"]}
        )
        self.assertFalse(models.LeaderSignUp.objects.filter(trip=trip).exists())

    def test_trip_must_allow_leader_signups(self):
        trip = factories.TripFactory.create(
            allow_leader_signups=False,
            # No particular type leader rating is required to lead;
            # Leaders of *any* type can attend
            program=enums.Program.NONE.value,
            # No notes required
            notes='',
        )
        self.participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=self.participant,
                activity=enums.Activity.HIKING.value,
            )
        )
        self.assertTrue(self.participant.can_lead(trip.program_enum))

        resp = self.client.post('/trips/signup/leader/', {'trip': trip.pk})
        self.assertEqual(
            resp.context['form'].errors,
            {'__all__': ['Trip is not currently accepting leader signups.']},
        )
        self.assertFalse(models.LeaderSignUp.objects.filter(trip=trip).exists())

        # However, if we enable the setting, the participant can indeed sign up
        trip.allow_leader_signups = True
        trip.save()
        self.client.post('/trips/signup/leader/', {'trip': trip.pk})
        models.LeaderSignUp.objects.get(trip=trip, participant=self.participant)
        self.assertIn(self.participant, trip.leaders.all())

    def test_signup_exists_but_no_longer_leader(self):
        """Test the edge case where the user *was* signed up as a leader, but no longer is."""
        trip = factories.TripFactory.create(
            allow_leader_signups=True,
            program=enums.Program.NONE.value,
            notes='',
        )
        self.participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=self.participant,
                activity=enums.Activity.HIKING.value,
            )
        )

        self.client.post('/trips/signup/leader/', {'trip': trip.pk})
        self.assertTrue(models.LeaderSignUp.objects.filter(trip=trip).exists())

        trip.leaders.clear()
        resp = self.client.post('/trips/signup/leader/', {'trip': trip.pk})
        soup = BeautifulSoup(resp.content, 'html.parser')
        warning = soup.find(class_='alert-danger')
        # Note: This is a temporary solution.
        # In the future, leaders should be able to self-add themselves back.
        self.assertEqual(
            strip_whitespace(warning.text),
            'Already signed up as a leader on this trip! Contact the trip organizer to be re-added.',
        )


class DeleteSignupViewTest(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)
        super().setUp()

    def test_get(self):
        """You cannot delete via a GET (could be exploited by malicious users)."""
        signup = factories.SignUpFactory.create(participant=self.participant)
        resp = self.client.get(f'/signups/{signup.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/trips/{signup.trip.pk}/')
        self.assertTrue(models.SignUp.objects.filter(pk=signup.pk).exists())

    def test_must_be_logged_in(self):
        signup = factories.SignUpFactory.create()
        self.client.logout()
        resp = self.client.post(f'/signups/{signup.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url, f'/accounts/login/?next=/signups/{signup.pk}/delete/'
        )
        self.assertTrue(models.SignUp.objects.filter(pk=signup.pk).exists())

    def test_cannot_delete_somebody_elses(self):
        other_signup = factories.SignUpFactory.create()
        resp = self.client.post(f'/signups/{other_signup.pk}/delete/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(models.SignUp.objects.filter(pk=other_signup.pk).exists())

    def test_cannot_drop_if_trip_forbids_it(self):
        trip = factories.TripFactory.create(
            let_participants_drop=False, algorithm='fcfs'
        )
        signup = factories.SignUpFactory.create(participant=self.participant, trip=trip)
        resp = self.client.post(f'/signups/{signup.pk}/delete/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(models.SignUp.objects.filter(pk=signup.pk).exists())

    def test_can_always_drop_off_during_lottery(self):
        trip = factories.TripFactory.create(
            let_participants_drop=False, algorithm='lottery'
        )
        signup = factories.SignUpFactory.create(participant=self.participant, trip=trip)
        resp = self.client.post(f'/signups/{signup.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/trips/')
        self.assertFalse(models.SignUp.objects.filter(pk=signup.pk).exists())

    def test_can_drop_off_if_trip_allows_it(self):
        trip = factories.TripFactory.create(
            let_participants_drop=True, algorithm='fcfs'
        )
        signup = factories.SignUpFactory.create(participant=self.participant, trip=trip)
        resp = self.client.post(f'/signups/{signup.pk}/delete/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/trips/')
        self.assertFalse(models.SignUp.objects.filter(pk=signup.pk).exists())
