from datetime import date, datetime

from bs4 import BeautifulSoup
from django.template import Context, Template
from freezegun import freeze_time

from ws import enums, models
from ws.tests import TestCase, factories
from ws.utils.dates import localize


@freeze_time("11 Dec 2025 12:00:00 EST")
class SignupForTripTests(TestCase):
    @staticmethod
    def _make_trip(**kwargs):
        """ Create an upcoming FCFS trip. """
        trip_kwargs = {
            'name': "Some Cool Upcoming Trip",
            'trip_date': date(2025, 12, 14),
            'signups_open_at': localize(datetime(2025, 12, 10, 12, 0)),
            'signups_close_at': localize(datetime(2025, 12, 13, 21, 30)),
            'algorithm': 'fcfs',
            **kwargs,
        }
        return factories.TripFactory.create(**trip_kwargs)

    @staticmethod
    def _leader(activity):
        participant = factories.ParticipantFactory()
        participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=participant, activity=activity
            )
        )
        return participant

    def _render(self, participant, trip=None):
        trip = trip or self._make_trip()
        existing_signup = trip.signup_set.filter(participant=participant).first()
        context = Context(
            {
                'trip': trip,
                'participant': participant,
                'user': participant.user,
                'existing_signup': existing_signup,
            }
        )
        html_template = Template(
            '{% load signup_tags %}{% signup_for_trip trip participant existing_signup %}'
        )
        raw_html = html_template.render(context)
        return BeautifulSoup(raw_html, 'html.parser')

    def test_participant_with_problems_must_correct_them_first(self):
        # Make a Participant without a full name (we require one)
        participant = factories.ParticipantFactory.create(name='Houdini')
        self.assertFalse(participant.profile_allows_trip_attendance)

        soup = self._render(participant)

        text = soup.find(class_='alert-danger').get_text(' ', strip=True)
        self.assertIn(
            'cannot sign up for trips without current personal information', text
        )

    def test_wimp_cannot_sign_up_for_trip(self):
        """" You can't be the emergency contact while attending a trip. """
        wimp_participant = factories.ParticipantFactory.create()
        trip = self._make_trip(wimp=wimp_participant)

        soup = self._render(wimp_participant, trip)

        alert = soup.find(class_='alert-info').get_text(' ', strip=True)
        self.assertIn('Signups are open!', alert)
        self.assertIn("you cannot sign up as you're currently the WIMP", alert)
        self.assertIsNone(soup.find('form'))

    def test_leader_signup_allowed_for_open_activities(self):
        """ Any leader can sign up as a leader for open program trips. """
        circus_trip = self._make_trip(
            allow_leader_signups=True,
            activity=models.LeaderRating.CIRCUS,
            program=enums.Program.CIRCUS.value,
        )
        self.assertTrue(circus_trip.signups_open)
        leader = self._leader(models.LeaderRating.CLIMBING)

        soup = self._render(leader, circus_trip)
        self.assertTrue(
            soup.find('button', type='submit', text='Sign up as participant')
        )
        self.assertTrue(soup.find('button', type='submit', text='Sign up as leader'))

    def test_leaders_with_rating_can_sign_up(self):
        """ Leaders with an active rating in the activity can sign up as leaders. """
        climbing_trip = self._make_trip(
            allow_leader_signups=True,
            activity=models.LeaderRating.CLIMBING,
            program=enums.Program.CLIMBING.value,
        )
        climbing_leader = self._leader(models.LeaderRating.CLIMBING)

        climbing_soup = self._render(climbing_leader, climbing_trip)
        self.assertTrue(
            climbing_soup.find('button', type='submit', text='Sign up as participant')
        )
        self.assertTrue(
            climbing_soup.find('button', type='submit', text='Sign up as leader')
        )

        hiking_leader = self._leader(models.LeaderRating.HIKING)
        soup = self._render(hiking_leader, climbing_trip)
        self.assertTrue(soup.find('button', type='submit', text='Sign up'))
        self.assertFalse(soup.find('button', type='submit', text='Sign up as leader'))

    def test_not_yet_open(self):
        trip = self._make_trip(
            signups_open_at=localize(datetime(2025, 12, 12, 13, 45)),
            signups_close_at=localize(datetime(2025, 12, 13, 23, 59)),
            allow_leader_signups=True,
            activity=models.LeaderRating.BIKING,
            program=enums.Program.BIKING.value,
        )
        self.assertTrue(trip.signups_not_yet_open)

        # Note that normal participants cannot sign up
        participant = factories.ParticipantFactory()
        soup = self._render(participant, trip)
        self.assertEqual(
            soup.find(class_='alert-info').get_text(' ', strip=True),
            'Signups for this trip are not yet open.',
        )
        self.assertIsNone(soup.find('form'))

        # Make that same participant into a leader!
        rating = factories.LeaderRatingFactory.create(
            participant=participant, activity=models.LeaderRating.BIKING
        )
        participant.leaderrating_set.add(rating)
        leader_soup = self._render(participant, trip)
        self.assertEqual(
            leader_soup.find(class_='alert-info').get_text(' ', strip=True),
            'Signups for this trip are not yet open.',
        )
        self.assertTrue(participant.is_leader)

        # The trip is upcoming, allows leader signups, and the participant can lead biking trips!
        self.assertEqual(
            leader_soup.find(class_='alert-success').get_text(' ', strip=True),
            'However, you can sign up early as a leader!',
        )
        self.assertTrue(leader_soup.find('form'))

    def test_closed_trip(self):
        """ Nobody may sign up after signups close. """
        trip = self._make_trip(
            signups_close_at=localize(datetime(2025, 12, 11, 11, 11))
        )
        self.assertTrue(trip.signups_closed)
        soup = self._render(factories.ParticipantFactory(), trip)
        self.assertEqual(
            soup.find(class_='alert-info').get_text(' ', strip=True),
            'Signups for this trip are closed.',
        )
        self.assertIsNone(soup.find('form'))

    def test_already_signed_up(self):
        """ We prohibit people from signing up twice. """
        trip = self._make_trip()
        signup = factories.SignUpFactory.create(trip=trip, on_trip=True)
        self.assertTrue(trip.upcoming)

        soup = self._render(signup.participant, trip)
        self.assertIsNone(soup.find('form'))
        self.assertEqual(
            soup.find(class_='alert-success').get_text(' ', strip=True),
            'You are signed up for this trip.',
        )
        self.assertTrue(
            soup.find(
                'p',
                text='If you can no longer attend this trip, let your leaders know.',
            )
        )

    def test_signed_up_for_lottery_trip_but_may_drop(self):
        """ Participants can always drop off of lottery trips. """
        trip = self._make_trip(algorithm='lottery', let_participants_drop=False)
        signup = factories.SignUpFactory.create(trip=trip, on_trip=False)

        soup = self._render(signup.participant, trip)

        msg = soup.find(class_='alert-success').get_text(' ', strip=True)
        self.assertIn("You're signed up for this trip's lottery.", msg)
        self.assertIn("You'll find out if you have a spot after the lottery runs.", msg)

        self.assertIsNone(soup.find('form'))
        self.assertTrue(soup.find('delete', attrs={'data-label': 'Drop off trip'}))

    def test_signed_up_for_fcfs_trip_but_may_drop(self):
        """ FCFS trips can optionally support dropping off. """
        trip = self._make_trip(algorithm='fcfs', let_participants_drop=True)
        signup = factories.SignUpFactory.create(trip=trip, on_trip=True)

        soup = self._render(signup.participant, trip)
        self.assertIsNone(soup.find('form'))
        self.assertTrue(soup.find('delete', attrs={'data-label': 'Drop off trip'}))
