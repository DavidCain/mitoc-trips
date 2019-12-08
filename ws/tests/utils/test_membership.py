from collections import OrderedDict
from datetime import date
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.db.utils import OperationalError
from freezegun import freeze_time

from ws import enums
from ws.tests import TestCase, factories
from ws.utils import geardb, membership


class UpdateMembershipCacheTest(TestCase):
    @freeze_time("2019-03-12 11:31:22 EST")
    def test_membership_found(self):
        user = factories.UserFactory.create(email='foobarbaz@example.com')
        participant = factories.ParticipantFactory.create(membership=None, user=user)

        active_membership = {
            'membership': {
                'expires': date(2020, 3, 18),
                'active': True,
                'email': 'foobarbaz@example.com',
            },
            'waiver': {'expires': date(2020, 3, 9), 'active': True},
            'status': 'Active',
        }

        with mock.patch.object(geardb, 'matching_memberships') as all_matches:
            all_matches.return_value = OrderedDict(
                {'foobarbaz@example.com': active_membership}
            )

            membership.update_membership_cache(participant)

        all_matches.assert_called_once()
        self.assertCountEqual(
            all_matches.call_args_list[0][0][0], ['foobarbaz@example.com']
        )
        participant.refresh_from_db()
        self.assertEqual(participant.membership.membership_expires, date(2020, 3, 18))
        self.assertEqual(participant.membership.waiver_expires, date(2020, 3, 9))

    def test_no_recent_membership_found(self):
        user = factories.UserFactory.create(email='primary@example.com')
        factories.EmailFactory.create(
            user=user, email='secondary@example.com', verified=True, primary=False
        )

        # This unverified email won't be used.
        factories.EmailFactory.create(
            user=user, email='unverified@example.com', verified=False, primary=False
        )

        participant = factories.ParticipantFactory.create(membership=None, user=user)

        with mock.patch.object(geardb, 'membership_expiration') as mem_exp:
            mem_exp.return_value = {
                'membership': {'expires': None, 'active': False, 'email': None},
                'waiver': {'expires': None, 'active': False},
                'status': 'Missing',
            }
            membership.update_membership_cache(participant)

        mem_exp.assert_called_once()
        self.assertCountEqual(
            mem_exp.call_args_list[0][0][0],
            ['primary@example.com', 'secondary@example.com'],
        )
        participant.refresh_from_db()
        self.assertIsNone(participant.membership.membership_expires)
        self.assertIsNone(participant.membership.waiver_expires)

    def test_refresh_targets(self):
        """ We refresh any participant without a membership or with a stale cache. """
        # Participant has no cached membership!
        no_membership_participant = factories.ParticipantFactory.create(membership=None)

        # Participant was cached a bit over a week ago
        with freeze_time("2019-03-12 11:31:22 EST"):
            active_but_cached_last_week = factories.MembershipFactory.create(
                membership_expires=date(2020, 3, 18), waiver_expires=date(2020, 3, 18)
            )
        stale_participant = factories.ParticipantFactory.create(
            membership=active_but_cached_last_week
        )

        # Participant has no waiver & an expired membership, but that's recently true!
        cached_now = factories.MembershipFactory.create(
            membership_expires=None, waiver_expires=date(2019, 1, 1)
        )
        factories.ParticipantFactory.create(membership=cached_now)

        with mock.patch.object(membership, 'update_membership_cache') as update_cache:
            membership.refresh_all_membership_cache()

        update_cache.assert_has_calls(
            [mock.call(stale_participant), mock.call(no_membership_participant)],
            any_order=True,
        )
        self.assertEqual(update_cache.call_count, 2)  # recent participant was omitted!


@freeze_time("2019-03-19 14:30:00 EST")
class RefreshAllMembershipCacheTest(TestCase):
    def test_refresh_targets(self):
        """ We refresh any participant without a membership or with a stale cache. """
        # Participant has no cached membership!
        no_membership_participant = factories.ParticipantFactory.create(membership=None)

        # Participant was cached a bit over a week ago
        with freeze_time("2019-03-12 11:31:22 EST"):
            active_but_cached_last_week = factories.MembershipFactory.create(
                membership_expires=date(2020, 3, 18), waiver_expires=date(2020, 3, 18)
            )
        stale_participant = factories.ParticipantFactory.create(
            membership=active_but_cached_last_week
        )

        # Participant has no waiver & an expired membership, but that's recently true!
        cached_now = factories.MembershipFactory.create(
            membership_expires=None, waiver_expires=date(2019, 1, 1)
        )
        factories.ParticipantFactory.create(membership=cached_now)

        with mock.patch.object(membership, 'update_membership_cache') as update_cache:
            membership.refresh_all_membership_cache()

        update_cache.assert_has_calls(
            [mock.call(stale_participant), mock.call(no_membership_participant)],
            any_order=True,
        )
        self.assertEqual(update_cache.call_count, 2)  # recent participant was omitted!


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
        with mock.patch.object(membership, 'update_membership_cache') as update_cache:
            self.assertTrue(self._can_attend(participant.user))

        # The membership we had on file was plenty, we did not need to update the cache!
        update_cache.assert_not_called()

    def test_fails_to_update_cache(self):
        """ If the gear database is down, we just allow participants to attend. """
        participant = factories.ParticipantFactory.create(membership=None)

        with mock.patch.object(membership, 'update_membership_cache') as update_cache:
            update_cache.side_effect = OperationalError  # (db error)
            self.assertTrue(self._can_attend(participant.user))

        update_cache.assert_called_once_with(participant)

    def test_cache_updated(self):
        """ If our local cache is outdated, we must hit the gear database for updates. """
        with freeze_time("2018-10-23 14:55:45 EST"):  # (Will have old `last_cached`)
            dated_membership = factories.MembershipFactory.create(
                membership_expires=date(2018, 11, 18),  # Active, expires before trip
                waiver_expires=date(2018, 12, 18),  # Active, expires after trip
            )
        participant = factories.ParticipantFactory.create(membership=dated_membership)
        before_refreshing_ts = dated_membership.last_cached

        # Right now, with our last-cached copy of their membership, they cannot attend
        self.assertCountEqual(
            participant.reasons_cannot_attend(self.trip),
            [enums.TripIneligibilityReason.MEMBERSHIP_NEEDS_RENEWAL],
        )

        def update_participant_membership(par):
            """ Update the membership record (as if they'd renewed today!) """
            par.update_membership(
                membership_expires=date(2019, 11, 19), waiver_expires=date(2019, 11, 19)
            )

        with mock.patch.object(membership, 'update_membership_cache') as update_cache:
            update_cache.side_effect = update_participant_membership
            # Tick forward in time so we can show that `last_cached` ts advances!
            with freeze_time("2018-11-19 12:00:00 EST", tick=True):
                can_attend = self._can_attend(participant.user)

        self.assertTrue(can_attend)
        update_cache.assert_called_once_with(participant)

        # The participant now has an updated membership cache too!
        dated_membership.refresh_from_db()
        self.assertGreater(dated_membership.last_cached, before_refreshing_ts)
        self.assertEqual(dated_membership.membership_expires, date(2019, 11, 19))
        self.assertEqual(dated_membership.waiver_expires, date(2019, 11, 19))

        self.assertFalse(any(participant.reasons_cannot_attend(self.trip)))
