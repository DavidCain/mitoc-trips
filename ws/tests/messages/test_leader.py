from datetime import date
from unittest import mock

from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time

from ws import models
from ws.messages import leader
from ws.tests import factories
from ws.tests.messages import MessagesTestCase


class NotALeaderMessagesTest(MessagesTestCase):
    """For users that are not leaders, we never emit any messages."""

    def test_anonymous_user(self):
        request = self.factory.get("/")

        # Simulate the effects of the ParticipantMiddleware for an anonymous user
        request.user = AnonymousUser()
        request.participant = None

        with self._mock_add_message() as add_message:
            leader.Messages(request).supply()

        add_message.assert_not_called()

    def test_user_but_no_participant_on_request(self):
        request = self.factory.get("/")

        # Simulate the effects of the ParticipantMiddleware for a known user
        request.user = factories.UserFactory.create()
        request.participant = None

        with self._mock_add_message() as add_message:
            leader.Messages(request).supply()

        add_message.assert_not_called()

    def test_participant_not_a_leader(self):
        request = self.factory.get("/")

        # Simulate the effects of the ParticipantMiddleware for a known participant
        participant = factories.ParticipantFactory.create()
        request.participant = participant
        request.user = participant.user

        with self._mock_add_message() as add_message:
            leader.Messages(request).supply()

        add_message.assert_not_called()


class LeaderMessagesTest(MessagesTestCase):
    """Test messages emitted to Winter School leaders."""

    @property
    def _leader(self):
        trip_leader = factories.ParticipantFactory()
        trip_leader.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=trip_leader, activity=models.LeaderRating.WINTER_SCHOOL
            )
        )
        return trip_leader

    @freeze_time("2020-01-15 14:56:00 EST")
    def test_complain_if_missing_feedback(self):
        """We warn leaders about recent trips missing feedback."""
        trip_leader = self._leader

        # Create a trip that's too old for us to care about missing feedback
        too_old = factories.TripFactory.create(trip_date=date(2019, 12, 12))
        too_old.leaders.add(trip_leader)
        factories.SignUpFactory.create(trip=too_old, on_trip=True)

        # Create a recent trip missing feedback
        recent_missing = factories.TripFactory.create(
            pk=2239, name="Radness", trip_date=date(2020, 1, 4)
        )
        recent_missing.leaders.add(trip_leader)
        factories.SignUpFactory.create(trip=recent_missing, on_trip=True)

        # Create a recent trip, but with no signups!
        no_signups = factories.TripFactory.create(trip_date=date(2020, 1, 4))
        self.assertFalse(no_signups.on_trip_or_waitlisted)
        no_signups.leaders.add(trip_leader)

        # Create a recent trip with feedback present
        has_feedback = factories.TripFactory.create(trip_date=date(2020, 1, 11))
        has_feedback.leaders.add(trip_leader)
        signup1 = factories.SignUpFactory.create(trip=has_feedback, on_trip=True)
        signup2 = factories.SignUpFactory.create(trip=has_feedback, on_trip=True)
        for signup in [signup1, signup2]:
            factories.FeedbackFactory.create(
                leader=trip_leader, trip=has_feedback, participant=signup.participant
            )

        request = self.factory.get("/")
        request.participant = trip_leader
        request.user = trip_leader.user

        with self._mock_add_message() as add_message:
            leader.Messages(request).supply()

        # We only warn about the recent trip lacking feedback!
        msg = 'Please supply feedback for <a href="/trips/2239/review/">Radness</a>'
        add_message.assert_called_once_with(
            request, messages.WARNING, msg, extra_tags="safe"
        )

    @freeze_time("2020-01-17 14:56:00 EST")
    def test_complain_if_missing_itineraries(self):
        """We warn leaders current/future trips missing itineraries."""
        trip_leader = self._leader

        # Create 4 trips that are missing itineraries
        yesterday = factories.TripFactory.create(trip_date=date(2020, 1, 16))
        today = factories.TripFactory.create(
            pk=9213, name="Today", trip_date=date(2020, 1, 17)
        )
        tomorrow = factories.TripFactory.create(
            pk=9214, name="Tomorrow", trip_date=date(2020, 1, 18)
        )
        next_week = factories.TripFactory.create(trip_date=date(2020, 1, 25))
        for trip in [yesterday, today, tomorrow, next_week]:
            trip.leaders.add(trip_leader)

        # Create an upcoming trip that does have an itinerary!
        with_info = factories.TripFactory.create(
            trip_date=date(2020, 1, 19), info=factories.TripInfoFactory.create()
        )
        with_info.leaders.add(trip_leader)

        request = self.factory.get("/")
        request.participant = trip_leader
        request.user = trip_leader.user

        with self._mock_add_message() as add_message:
            leader.Messages(request).supply()

        # Note that we ask for itineraries on the immediate upcoming trips
        # Excluded are the past trip & the too-distant future trip
        add_message.assert_has_calls(
            [
                mock.call(
                    request,
                    messages.WARNING,
                    'Please <a href="/trips/9213/itinerary/">submit an itinerary for Today</a> before departing!',
                    extra_tags="safe",
                ),
                mock.call(
                    request,
                    messages.WARNING,
                    'Please <a href="/trips/9214/itinerary/">submit an itinerary for Tomorrow</a> before departing!',
                    extra_tags="safe",
                ),
            ]
        )
