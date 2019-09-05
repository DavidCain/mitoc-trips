from datetime import date
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.db.utils import OperationalError
from freezegun import freeze_time

from ws import models
from ws.tests import TestCase, factories
from ws.utils import membership


@freeze_time("2019-03-19 14:30:00 EST")
class RefreshAllMembershipCache(TestCase):
    def test_refresh_targets(self):
        """ We refresh any participant without a membership or with a stale cache. """
        # Participant has no cached membership!
        no_membership_participant = factories.ParticipantFactory.create()
        self.assertIsNone(no_membership_participant.membership)

        # Participant was cached a bit over a week ago
        with freeze_time("2019-03-12 11:31:22 EST"):
            active_but_cached_last_week = models.Membership.objects.create(
                membership_expires=date(2020, 3, 18), waiver_expires=date(2020, 3, 18)
            )
        stale_participant = factories.ParticipantFactory.create(
            membership=active_but_cached_last_week
        )

        # Participant has no waiver & an expired membership, but that's recently true!
        cached_now = models.Membership.objects.create(
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
            trip_date=date(2018, 11, 30), algorithm='fcfs', membership_required=True
        )

    def _can_attend(self, user):
        return membership.can_attend_trip(user, self.trip)

    def test_anonymous_user_cannot_attend(self):
        self.assertFalse(self._can_attend(AnonymousUser()))

    def test_participant_with_current_membership_can_attend(self):
        # Create a participant with a membership valid for the given trip
        participant = factories.ParticipantFactory.create(
            membership=models.Membership.objects.create(
                membership_expires=date(2019, 11, 12), waiver_expires=date(2019, 11, 12)
            )
        )
        self.assertTrue(participant.can_attend(self.trip))

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
            dated_membership = models.Membership.objects.create(
                membership_expires=date(2018, 11, 18),  # Active, expires before trip
                waiver_expires=date(2018, 12, 18),  # Active, expires after trip
            )
        participant = factories.ParticipantFactory.create(membership=dated_membership)

        # Right now, with our last-cached copy of their membership, they cannot attend
        self.assertFalse(participant.can_attend(self.trip))

        def update_participant_membership(par):
            """ Update the membership record (as if they'd renewed today!) """
            par.update_membership(
                membership_expires=date(2019, 11, 19), waiver_expires=date(2019, 11, 19)
            )

        with mock.patch.object(membership, 'update_membership_cache') as update_cache:
            update_cache.side_effect = update_participant_membership
            self.assertTrue(self._can_attend(participant.user))

        update_cache.assert_called_once_with(participant)

        # The participant now has an updated membership cache too!
        dated_membership.refresh_from_db()
        self.assertEqual(dated_membership.membership_expires, date(2019, 11, 19))
        self.assertEqual(dated_membership.waiver_expires, date(2019, 11, 19))
