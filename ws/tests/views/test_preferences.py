import contextlib
from datetime import date, datetime
from unittest import mock

from bs4 import BeautifulSoup
from django.contrib import messages
from django.test import TestCase
from freezegun import freeze_time

from ws import enums, models, unsubscribe
from ws.tests import factories, strip_whitespace


class LotteryPairingViewTests(TestCase):
    def test_authenticated_users_only(self):
        """Users must be signed in to set lottery pairing."""
        response = self.client.get("/preferences/lottery/pairing/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, "/accounts/login/?next=/preferences/lottery/pairing/"
        )

    def test_users_with_info_only(self):
        """Participant records are required."""
        user = factories.UserFactory.create()
        self.client.force_login(user)
        response = self.client.get("/preferences/lottery/pairing/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, "/profile/edit/?next=/preferences/lottery/pairing/"
        )

    def test_cannot_pair_with_self(self):
        """For obvious reasons, attempting to "pair up" with yourself is forbidden."""
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        response = self.client.post(
            "/preferences/lottery/pairing/", {"paired_with": par.pk}
        )
        self.assertTrue(response.context["form"].errors["paired_with"])

        # No lottery information is saved
        with self.assertRaises(models.LotteryInfo.DoesNotExist):
            par.lotteryinfo  # pylint: disable=pointless-statement  # noqa: B018

    def test_can_change_pairing(self):
        """Participants can change their pairing choices."""
        other_par = factories.ParticipantFactory.create()
        par = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=par, paired_with=other_par)
        self.client.force_login(par.user)
        self.client.post("/preferences/lottery/pairing/", {"paired_with": ""})

        # The participant is now no longer paired
        par.lotteryinfo.refresh_from_db()
        self.assertIsNone(par.lotteryinfo.paired_with)

    def test_non_reciprocated_pairing(self):
        """We handle a participant requesting pairing from somebody who hasn't done the same."""
        par = factories.ParticipantFactory.create()
        other_par = factories.ParticipantFactory.create(name="Freddie Mercury")
        self.client.force_login(par.user)
        with mock.patch.object(messages, "info") as info:
            self.client.post(
                "/preferences/lottery/pairing/", {"paired_with": other_par.pk}
            )

        info.assert_called_once_with(
            mock.ANY,  # (Request object)
            "Freddie Mercury must also select to be paired with you.",
        )

        self.assertEqual(par.lotteryinfo.paired_with, other_par)
        self.assertFalse(par.lotteryinfo.reciprocally_paired_with)

    def test_reciprocated_pairing(self):
        """We handle a participant being the second half to request pairing."""
        par = factories.ParticipantFactory.create()
        other_par = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=other_par, paired_with=par)

        self.client.force_login(par.user)
        with mock.patch.object(messages, "info") as info:
            self.client.post(
                "/preferences/lottery/pairing/", {"paired_with": other_par.pk}
            )

        info.assert_called_once()
        msg = info.call_args[0][1]
        self.assertTrue(
            msg.startswith("You must both sign up for trips you're interested in:")
        )

        self.assertEqual(par.lotteryinfo.paired_with, other_par)
        self.assertTrue(par.lotteryinfo.reciprocally_paired_with)


class LotteryPrefsPostHelper:
    def _post(self, json_data):
        return self.client.post(
            "/preferences/lottery/",
            json_data,
            content_type="application/json",
        )


class LotteryPreferencesDriverStatusTests(TestCase, LotteryPrefsPostHelper):
    def test_bad_lottery_form(self):
        """The lottery form must have all its keys specified."""
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)
        self.assertEqual(self._post({}).status_code, 400)
        self.assertEqual(self._post({"signups": []}).status_code, 400)

    def test_no_car_no_trips_no_pairing(self):
        """Test the simplest submission of a user with no real preferences to express."""
        with freeze_time("2019-01-15 12:25:00 EST"):
            par = factories.ParticipantFactory.create(lotteryinfo=None)

            self.client.force_login(par.user)
            response = self._post({"signups": [], "car_status": "none"})

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, "none")
        self.assertIsNone(par.lotteryinfo.number_of_passengers)
        self.assertIsNone(par.lotteryinfo.paired_with)
        self.assertEqual(
            par.lotteryinfo.last_updated,
            datetime.fromisoformat("2019-01-15T12:25:00-05:00"),
        )

    def test_can_drive_new_car(self):
        """Participants who own a car can express their willingness to drive."""
        with freeze_time("2019-01-15 12:25:00 EST"):
            par = factories.ParticipantFactory.create(lotteryinfo=None, car=None)

            self.client.force_login(par.user)
            response = self._post(
                {
                    "signups": [],
                    "car_status": "own",
                    "number_of_passengers": 4,
                },
            )

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, "own")
        self.assertEqual(par.lotteryinfo.number_of_passengers, 4)

        # Participant still isn't paired with anybody
        self.assertIsNone(par.lotteryinfo.paired_with)

    def test_willing_to_rent(self):
        """Participants can express a willingness to rent."""
        par = factories.ParticipantFactory.create(lotteryinfo=None, car=None)

        self.client.force_login(par.user)
        response = self._post(
            {"signups": [], "car_status": "rent", "number_of_passengers": 3},
        )

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, "rent")
        self.assertEqual(par.lotteryinfo.number_of_passengers, 3)
        self.assertIsNone(par.car)

    def test_willing_to_rent_unknown_seats(self):
        """It's valid to not know how many passengers your car would seat.

        It makes sense that if you're willing to rent, you can't know in
        advance how many people a hypothetical car would seat.
        """
        par = factories.ParticipantFactory.create(lotteryinfo=None, car=None)

        self.client.force_login(par.user)
        response = self._post(
            {"signups": [], "car_status": "rent", "number_of_passengers": None},
        )

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, "rent")
        self.assertIsNone(par.lotteryinfo.number_of_passengers)
        self.assertIsNone(par.car)


@freeze_time("2019-01-08 12:25:00 EST")
class LotteryPreferencesSignupTests(TestCase, LotteryPrefsPostHelper):
    def test_missing_ordering(self):
        """Signups must specify signup ID, deletion, and ordering."""
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)

        signup = factories.SignUpFactory.create(
            participant=par,
            trip__algorithm="lottery",
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        response = self._post(
            {
                "signups": [
                    # No ordering given
                    {"id": signup.pk, "deleted": False},
                ],
                "car_status": "none",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"message": "Unable to save signups"})

    def test_invalid_ordering(self):
        """Ordering must be null or numeric."""
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)

        signup = factories.SignUpFactory.create(
            participant=par,
            trip__algorithm="lottery",
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        response = self._post(
            {
                "signups": [{"id": signup.pk, "deleted": False, "order": "threeve"}],
                "car_status": "none",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"message": "Unable to save signups"})

    def test_default_ranking(self):
        """By default, we list ranked signups by time of creation."""
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        okay, fave, hate = (
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm="lottery",
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
                trip__name=name,
            )
            for name in ["So-so", "Amazing", "Blech"]
        )

        # Signups for other types of trips are excluded; only upcoming WS trips
        factories.SignUpFactory.create(
            participant=par,
            trip__algorithm="lottery",
            trip__program=enums.Program.HIKING.value,
            trip__trip_date=date(2019, 3, 12),
        )
        factories.SignUpFactory.create(
            participant=par,
            trip__algorithm="lottery",
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 7),
        )
        # Of course, another participant's signups aren't counted
        factories.SignUpFactory.create(
            trip__algorithm="lottery",
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        self.client.force_login(par.user)
        # We initially order signups by time of creation
        response = self.client.get("/preferences/lottery/")
        self.assertEqual(response.status_code, 200)
        expected = [
            {"id": okay.pk, "trip__id": okay.trip.pk, "trip__name": "So-so"},
            {"id": fave.pk, "trip__id": fave.trip.pk, "trip__name": "Amazing"},
            {"id": hate.pk, "trip__id": hate.trip.pk, "trip__name": "Blech"},
        ]
        self.assertEqual(response.context["ranked_signups"], expected)

    def test_delete_signups(self):
        """We allow participants to remove signups."""
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        keep, kill = (
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm="lottery",
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
                trip__name=name,
            )
            for name in ["Great trip", "Bad trip"]
        )

        self.client.force_login(par.user)
        response = self._post(
            {
                "signups": [
                    {"id": keep.pk, "deleted": False, "order": 1},
                    {"id": kill.pk, "deleted": True, "order": None},
                ],
                "car_status": "none",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(models.SignUp.objects.filter(pk=kill.pk).exists())

    def test_rank_signups(self):
        """Participants may manually rank their signups in order of preference."""
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        okay, fave, hate = (
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm="lottery",
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
                trip__name=name,
            )
            for name in ["So-so", "Amazing", "Blech"]
        )

        self.client.force_login(par.user)
        response = self._post(
            {
                "signups": [
                    {"id": hate.pk, "deleted": False, "order": 3},
                    {"id": fave.pk, "deleted": False, "order": 1},
                    {"id": okay.pk, "deleted": False, "order": 2},
                ],
                "car_status": "none",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [s.pk for s in par.signup_set.order_by("order")],
            [fave.pk, okay.pk, hate.pk],
        )

    def test_cannot_delete_others_signups(self):
        """For obvious reasons, participants should not be allowed to remove others' signups."""
        attacker = factories.ParticipantFactory.create()
        victim = factories.ParticipantFactory.create()

        other_signup = factories.SignUpFactory.create(
            participant=victim,
            trip__algorithm="lottery",
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        self.client.force_login(attacker.user)
        response = self._post(
            {
                "signups": [{"id": other_signup.pk, "deleted": True, "order": 1}],
                "car_status": "none",
            }
        )
        # We give a 200, even though we could possibly return a 403
        self.assertEqual(response.status_code, 200)
        self.assertTrue(models.SignUp.objects.filter(pk=other_signup.pk).exists())

    def test_can_only_delete_ws_lottery_signups(self):
        """Route must not provide an undocumented means to drop off trips.

        Deletion of signups should *only* be for signups where the user is not on
        the trip because it's in the lottery stage of a Winter School trip.
        """
        par = factories.ParticipantFactory.create()
        not_deletable = [
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm="fcfs",
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
            ),
            # An edge case, but it's technically possible to be pre-placed on a lottery trip
            factories.SignUpFactory.create(
                on_trip=True,
                participant=par,
                trip__algorithm="lottery",
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
            ),
        ]
        self.client.force_login(par.user)
        response = self._post(
            {
                "signups": [
                    {"id": signup.pk, "deleted": True, "order": None}
                    for signup in not_deletable
                ],
                "car_status": "none",
            }
        )
        # None of the specified signups were actually deleted
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            models.SignUp.objects.filter(pk__in=[s.pk for s in not_deletable]).count(),
            len(not_deletable),
        )

    def test_signups_as_paired(self):
        """We handle rankings from participants who are reciprocally paired.

        Specifically, when a paired participant ranks trips, we apply the rankings
        to *both* participants, and warn if there are any trips where just one
        of the two have signed up.
        """
        par = factories.ParticipantFactory.create()
        other_par = factories.ParticipantFactory.create(name="Ada Lovelace")

        factories.LotteryInfoFactory.create(participant=par, paired_with=other_par)
        factories.LotteryInfoFactory.create(participant=other_par, paired_with=par)

        # Both participants sign up for a mutual trip
        mutual_trip = factories.TripFactory.create()
        mutual = factories.SignUpFactory.create(participant=par, trip=mutual_trip)
        mutual_other = factories.SignUpFactory.create(
            participant=other_par, trip=mutual_trip
        )

        # Only our subject signs up for a separate trip
        only_one_trip = factories.TripFactory.create(name="Sweet Ice Climbing Trip")
        lone = factories.SignUpFactory.create(participant=par, trip=only_one_trip)

        self.client.force_login(par.user)
        with mock.patch.object(messages, "warning") as log_warning:
            self._post(
                {
                    "signups": [
                        {"id": mutual.pk, "deleted": False, "order": 2},
                        {"id": lone.pk, "deleted": False, "order": 1},
                    ],
                    "car_status": "none",
                }
            )

        log_warning.assert_called_once_with(
            mock.ANY, "Ada Lovelace hasn't signed up for Sweet Ice Climbing Trip."
        )

        # We accept the rankings for the participant's two signups
        self.assertEqual(
            [(s.pk, s.order) for s in par.signup_set.order_by("order")],
            [(lone.pk, 1), (mutual.pk, 2)],
        )
        # We save the ranking numbers on the other participant's signups too
        self.assertEqual(
            [(s.pk, s.order) for s in other_par.signup_set.order_by("order")],
            [(mutual_other.pk, 2)],
        )


class EmailPreferencesTest(TestCase):
    def _expect_success(
        self,
        par: models.Participant,
        msg: str,
        send_reminder: bool,
    ) -> None:
        """Whether opting in or out, success looks the same!"""
        self.client.force_login(par.user)

        with mock.patch.object(messages, "success") as success:
            response = self.client.post(
                "/preferences/email/",
                {"send_membership_reminder": send_reminder},
            )

        # Obviously, we updated the participant's preferences
        par.refresh_from_db()
        self.assertIs(par.send_membership_reminder, send_reminder)

        # We then communicate the change to them
        success.assert_called_once_with(
            mock.ANY,  # (Request object)
            msg,
        )

        # Finally, we redirect home
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")  # type: ignore[attr-defined]

    def test_authenticated_users_only(self):
        """Users must be signed in to set their email preferences."""
        response = self.client.get("/preferences/email/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=/preferences/email/")

    def test_users_with_participants_only(self):
        """Participant records are required (we need them to save a preference)."""
        user = factories.UserFactory.create()
        self.client.force_login(user)
        response = self.client.get("/preferences/email/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/profile/edit/?next=/preferences/email/")

    def test_opt_out(self):
        par = factories.ParticipantFactory.create(send_membership_reminder=True)
        self._expect_success(
            par,
            msg="Will not send any emails reminding you to remind your membership.",
            send_reminder=False,
        )

    def test_opt_out_even_though_never_opted_in(self):
        par = factories.ParticipantFactory.create(send_membership_reminder=False)
        self._expect_success(
            par,
            msg="Will not send any emails reminding you to remind your membership.",
            send_reminder=False,
        )

    def test_opt_into_reminders_before_paying(self):
        self._expect_success(
            factories.ParticipantFactory.create(membership=None),
            msg="If you sign up for a membership, we'll remind you when it's time to renew.",
            send_reminder=True,
        )

    @freeze_time("2019-01-15 12:25:00 EST")
    def test_opt_into_reminders_as_a_member(self):
        self._expect_success(
            factories.ParticipantFactory.create(
                membership__membership_expires=date(2019, 6, 1)
            ),
            msg="We'll send you an email on Apr 24, 2019 reminding you to renew.",
            send_reminder=True,
        )

    @freeze_time("2019-01-15 12:25:00 EST")
    def test_opt_into_reminders_as_an_expired_member(self):
        self._expect_success(
            factories.ParticipantFactory.create(
                membership__membership_expires=date(2019, 1, 1)
            ),
            msg="If you are current on dues, we'll remind you when it's time to renew.",
            send_reminder=True,
        )

    def test_stale_info_okay(self):
        """We don't make participants update their profiles just to edit email prefs."""
        with freeze_time("2019-01-15 12:00:00 EST"):
            par = factories.ParticipantFactory.create()

        self.client.force_login(par.user)

        with freeze_time("2021-01-15 12:00:00 EST"):
            self.assertIn(enums.ProfileProblem.STALE_INFO, par.problems_with_profile)

            # To demonstrate, we redirect on *other* views:
            demo = self.client.get("/preferences/lottery/")
            self.assertEqual(demo.status_code, 302)
            self.assertEqual(demo.url, "/profile/edit/?next=/preferences/lottery/")

            # But we won't redirect for updating email preferences.
            # Even though their information is stale, we won't redirect them to update.
            response = self.client.get("/preferences/email/")
            self.assertEqual(response.status_code, 200)


@freeze_time("2021-12-10 12:00:00 EST")
class EmailUnsubscribeTest(TestCase):
    @staticmethod
    @contextlib.contextmanager
    def _spy_on_add_message():
        patched = mock.patch.object(messages, "add_message", wraps=messages.add_message)
        with patched as add_message:
            yield add_message

    def _get(self, url: str) -> BeautifulSoup:
        response = self.client.get(url)
        assert response.status_code == 200
        return BeautifulSoup(response.content, "html.parser")

    def test_success_unauthenticated(self):
        """A user who is not logged in can use a token to unsubscribe."""
        par = factories.ParticipantFactory.create(
            pk=2348971, send_membership_reminder=True
        )
        token = "eyJwayI6MjM0ODk3MSwiZW1haWxzIjpbMF19:1mvjFY:KR-_sCXU64PeJjRtce4KeNr6gBACxl1QX50WzVgQQZ8"  # noqa: S105
        with self.settings(UNSUBSCRIBE_SECRET_KEY="sooper-secret"):  # noqa: S106
            with self._spy_on_add_message() as add_message:
                soup = self._get(f"/preferences/email/unsubscribe/{token}/")

        add_message.assert_called_once_with(
            mock.ANY, messages.SUCCESS, "Successfully unsubscribed"
        )
        par.refresh_from_db()
        self.assertFalse(par.send_membership_reminder)
        self.assertEqual(
            ["Successfully unsubscribed"],
            [alert.text.strip() for alert in soup.find_all(class_="alert")],
        )
        edit_link = soup.find("a", string="Edit your email preferences")
        self.assertTrue(edit_link)
        self.assertEqual(edit_link.attrs["href"], "/preferences/email/")

    def test_success_logged_in(self):
        """The token still works when logged in!."""
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        token = unsubscribe.generate_unsubscribe_token(par)
        with self._spy_on_add_message() as add_message:
            response = self.client.get(f"/preferences/email/unsubscribe/{token}/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/preferences/email/")

        add_message.assert_called_once_with(
            mock.ANY, messages.SUCCESS, "Successfully unsubscribed"
        )
        par.refresh_from_db()
        self.assertFalse(par.send_membership_reminder)

    def test_participant_since_deleted(self):
        """We handle the case of a valid token for a since-deleted participant."""
        par = factories.ParticipantFactory.create()
        token = unsubscribe.generate_unsubscribe_token(par)
        par.delete()
        soup = self._get(f"/preferences/email/unsubscribe/{token}/")
        self.assertEqual(
            ["Participant no longer exists"],
            [alert.text.strip() for alert in soup.find_all(class_="alert")],
        )
        self.assertTrue(soup.find("a", href="/preferences/email/"))
        self.assertEqual(
            strip_whitespace(soup.find("p", class_="lead").text),
            "Edit your email preferences (login required)",
        )

    def test_bad_token_not_logged_in(self):
        soup = self._get("/preferences/email/unsubscribe/bad_token/")
        self.assertEqual(
            ["Invalid token, cannot unsubscribe automatically."],
            [alert.text.strip() for alert in soup.find_all(class_="alert")],
        )
        self.assertTrue(soup.find("a", href="/preferences/email/"))
        self.assertEqual(
            strip_whitespace(soup.find("p", class_="lead").text),
            "Edit your email preferences (login required)",
        )

    def test_bad_token_but_logged_in(self):
        """If the participant has a bad token, but is logged in, let them manually opt out."""
        participant = factories.ParticipantFactory.create()
        self.client.force_login(participant.user)

        with self._spy_on_add_message() as add_message:
            response = self.client.get("/preferences/email/unsubscribe/bad_token/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/preferences/email/")

        add_message.assert_has_calls(
            [
                mock.call(
                    mock.ANY,
                    messages.ERROR,
                    "Invalid token, cannot unsubscribe automatically.",
                ),
                mock.call(
                    mock.ANY,
                    messages.INFO,
                    "However, you are logged in and can directly edit your mail preferences.",
                ),
            ],
            any_order=False,
        )

    def test_token_is_for_a_different_user(self):
        """If you clicked an unsubscribe link for a different participant, it should still work."""
        participant = factories.ParticipantFactory.create()
        token = unsubscribe.generate_unsubscribe_token(participant)

        self.client.force_login(factories.ParticipantFactory.create().user)

        with self._spy_on_add_message() as add_message:
            response = self.client.get(f"/preferences/email/unsubscribe/{token}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/preferences/email/")

        add_message.assert_has_calls(
            [
                mock.call(
                    mock.ANY,
                    messages.SUCCESS,
                    "Successfully unsubscribed",
                ),
                mock.call(
                    mock.ANY,
                    messages.WARNING,
                    "Note that the unsubscribe token was for a different participant! "
                    "You may edit your own mail preferences below.",
                ),
            ],
            any_order=False,
        )
