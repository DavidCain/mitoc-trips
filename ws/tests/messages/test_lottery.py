from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time

from ws import models
from ws.messages.lottery import Messages
from ws.tests import factories
from ws.tests.messages import MessagesTestCase
from ws.utils.dates import local_date


class LotteryMessagesTest(MessagesTestCase):
    @freeze_time("2017-01-17 12:00:00 EST")
    def test_anonymous_user_during_ws(self):
        """Anonymous users shouldn't receive lottery warnings."""
        request = self.factory.get("/")

        # Simulate the effects of the ParticipantMiddleware for an anonymous user
        request.user = AnonymousUser()
        request.participant = None

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_not_called()

    @freeze_time("2019-06-22 14:30:00 EST")
    def test_outside_ws(self):
        """These lottery messages don't do anything outside Winter School."""
        request = self._request_with_participant(factories.ParticipantFactory.create())

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_not_called()

    @freeze_time("2017-01-17 12:00:00 EST")
    def test_no_lottery_info(self):
        """During WS, we warn participants who haven't set lottery preferences."""
        par = factories.ParticipantFactory.create()
        with self.assertRaises(models.LotteryInfo.DoesNotExist):
            par.lotteryinfo  # pylint: disable=pointless-statement  # noqa: B018

        request = self._request_with_participant(par)
        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.WARNING,
            """You haven't set your <a href="/preferences/lottery/">lottery preferences</a>.""",
            extra_tags="safe",
        )

    @freeze_time("2017-01-17 12:00:00 EST")
    def test_driver_with_no_info(self):
        """We ask participants who said they could drive to supply info."""

        par = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=par, car_status="own")
        self.assertIsNone(par.car)

        request = self._request_with_participant(par)

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.WARNING,
            """You're a driver in the lottery, but haven't <a href="/profile/edit/">submitted car information</a>. """
            """If you can no longer drive, please update your <a href="/preferences/lottery/">lottery preferences</a>.""",
            extra_tags="safe",
        )

    def test_dated_info_last_marked_a_driver(self):
        """We remind participants if their lottery information is dated."""
        par = factories.ParticipantFactory.create()
        with freeze_time("2017-01-07 12:00:00 EST"):
            factories.LotteryInfoFactory.create(participant=par, car_status="rent")

        with freeze_time("2017-01-17 14:25:00 EST"):
            request = self._request_with_participant(par)
            with self._mock_add_message() as add_message:
                Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.INFO,
            """You haven't updated your <a href="/preferences/lottery/">lottery preferences</a> in 10 days. """
            "You will be counted as a driver in the next lottery.",
            extra_tags="safe",
        )

    def test_dated_info_last_marked_non_driver(self):
        """We remind participants if their lottery information is dated."""
        par = factories.ParticipantFactory.create()
        with freeze_time("2017-01-12 11:40:00 EST"):
            factories.LotteryInfoFactory.create(participant=par, car_status="none")

        with freeze_time("2017-01-17 13:25:00 EST"):
            request = self._request_with_participant(par)
            with self._mock_add_message() as add_message:
                Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.INFO,
            """You haven't updated your <a href="/preferences/lottery/">lottery preferences</a> in 5 days. """
            "You will be counted as a non-driver in the next lottery.",
            extra_tags="safe",
        )

    @staticmethod
    def _create_upcoming_ws_trip(participant, order=None):
        """Return an upcoming trip."""
        next_week = local_date() + timedelta(days=7)
        return factories.SignUpFactory.create(
            participant=participant,
            on_trip=False,
            order=order,
            # (Only upcoming WS lottery trips are considered)
            trip=factories.TripFactory.create(
                activity=models.BaseRating.WINTER_SCHOOL,
                algorithm="lottery",
                trip_date=next_week,
            ),
        )

    @freeze_time("2017-01-17 13:25:00 EST")
    def test_has_not_ranked(self):
        """If participants don't rank their signups, we warn them to do so."""
        par = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=par, car_status="none")
        request = self._request_with_participant(par)

        # We don't warn about ranking one trip
        self._create_upcoming_ws_trip(par, order=None)

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        # With two trips, we'll then warn that ranking should happen
        signup_2 = self._create_upcoming_ws_trip(par, order=None)

        with self._mock_add_message() as add_message:
            Messages(request).supply()
        add_message.assert_called_once_with(
            request,
            messages.WARNING,
            """You haven't <a href="/preferences/lottery/">ranked upcoming trips.</a>""",
            extra_tags="safe",
        )

        # If placed on this trip, the participant goes back to having just one un-ranked.
        # Now, we won't warn
        signup_2.on_trip = True
        signup_2.save()
        add_message.reset_mock()

        with self._mock_add_message() as add_message:
            Messages(request).supply()
        add_message.assert_not_called()

    def test_properly_configured(self):
        """Show that a WS participant with everything set up receives no warning."""
        with freeze_time("2017-01-15 13:25:00 EST"):
            par = factories.ParticipantFactory.create()
            factories.LotteryInfoFactory.create(participant=par, car_status="own")
            factories.CarFactory.create(participant=par)

            # Create (and rank) upcoming trips
            self._create_upcoming_ws_trip(par, order=1)
            self._create_upcoming_ws_trip(par, order=3)
            self._create_upcoming_ws_trip(par, order=2)

        with freeze_time("2017-01-17 13:25:00 EST"):
            request = self._request_with_participant(par)
            with self._mock_add_message() as add_message:
                Messages(request).supply()
        add_message.assert_not_called()
