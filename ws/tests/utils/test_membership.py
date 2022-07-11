from datetime import date

import responses
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time

from ws import enums
from ws.tests import TestCase, factories
from ws.utils import membership


@freeze_time("2018-11-19 12:00:00 EST")
class CanAttendTripTests(TestCase):
    def setUp(self):
        self.trip = factories.TripFactory.create(
            # (Hiking isn't special, we just choose to avoid WS-specific rules)
            program=enums.Program.HIKING.value,
            trip_date=date(2018, 11, 30),
            algorithm='fcfs',
            membership_required=True,
        )

    def _can_attend(self, user):
        return not any(membership.reasons_cannot_attend(user, self.trip))

    def test_anonymous_user_cannot_attend(self):
        self.assertFalse(self._can_attend(AnonymousUser()))

    def test_user_without_participant_cannot_attend(self):
        user = factories.UserFactory.create()

        self.assertCountEqual(
            membership.reasons_cannot_attend(user, self.trip),
            [enums.TripIneligibilityReason.NO_PROFILE_INFO],
        )

    def test_participant_with_current_membership_can_attend(self):
        # Create a participant with a membership valid for the given trip
        participant = factories.ParticipantFactory.create()
        self.assertFalse(any(participant.reasons_cannot_attend(self.trip)))

        # This participant can attend the trip!
        with responses.RequestsMock():  # No API call needed to get membership
            self.assertTrue(self._can_attend(participant.user))

    @responses.activate
    def test_fails_to_update_cache(self):
        """If the gear database is down, we just allow participants to attend."""
        participant = factories.ParticipantFactory.create(membership=None)

        responses.get(
            'https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/', status=500
        )
        self.assertTrue(self._can_attend(participant.user))

    @responses.activate
    def test_cache_updated(self):
        """If our local cache is outdated, we must hit the gear database for updates."""
        with freeze_time("2018-10-23 14:55:45 EST"):  # (Will have old `last_cached`)
            dated_membership = factories.MembershipFactory.create(
                membership_expires=date(2018, 11, 18),  # Active, expires before trip
                waiver_expires=date(2018, 12, 18),  # Active, expires after trip
            )
        participant = factories.ParticipantFactory.create(
            email='tim@mit.edu', membership=dated_membership
        )
        before_refreshing_ts = dated_membership.last_cached

        # Right now, with our last-cached copy of their membership, they cannot attend
        self.assertCountEqual(
            participant.reasons_cannot_attend(self.trip),
            [enums.TripIneligibilityReason.MEMBERSHIP_NEEDS_RENEWAL],
        )

        responses.get(
            url='https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=tim@mit.edu',
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "email": "tim@mit.edu",
                        "alternate_emails": ["timothy@example.com"],
                        "membership": {
                            "membership_type": "NA",
                            "expires": "2019-11-19",
                        },
                        "waiver": {"expires": "2019-11-19"},
                    }
                ],
            },
        )

        # Tick forward in time so we can show that `last_cached` ts advances!
        with freeze_time("2018-11-19 12:00:00 EST", tick=True):
            can_attend = self._can_attend(participant.user)

        self.assertTrue(can_attend)

        # The participant now has an updated membership cache too!
        dated_membership.refresh_from_db()
        self.assertGreater(dated_membership.last_cached, before_refreshing_ts)
        self.assertEqual(dated_membership.membership_expires, date(2019, 11, 19))
        self.assertEqual(dated_membership.waiver_expires, date(2019, 11, 19))

        self.assertFalse(any(participant.reasons_cannot_attend(self.trip)))
