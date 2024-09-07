from datetime import date, timedelta

from django.test import TestCase
from freezegun import freeze_time

from ws import cleanup, models, settings
from ws.tests import factories


def make_last_updated_on(participant, some_date):
    """Update the `profile_last_updated` field to be on some given date.

    We don't really care about the specific HMS on the day.

    This is helpful because:
    1. `profile_last_updated` is auto-set on new insertion, so we must update
       existing Participant records, rather than specifying at creation time.
    2. `profile_last_updated` is TZ-aware, but we can use TZ-naive dates
    """
    participant.profile_last_updated = participant.profile_last_updated.replace(
        year=some_date.year, month=some_date.month, day=some_date.day
    )
    participant.save()


class LapsedTests(TestCase):
    @freeze_time("Wed, 25 Dec 2019 12:00:00 EST")
    def test_not_lapsed_with_recent_update(self):
        today = date(2019, 12, 25)
        still_within_window = today - timedelta(
            days=settings.MUST_UPDATE_AFTER_DAYS - 1
        )
        factories.ParticipantFactory.create(profile_last_updated=still_within_window)

        self.assertEqual(len(cleanup.lapsed_participants()), 0)

    @freeze_time("Tue, 31 Dec 2019 23:59:00 EST")
    def test_dues_current(self):
        """MITOCers aren't lapsed if they have current dues, even with dated profile."""
        membership = models.Membership(
            membership_expires=date(2020, 1, 1),
            waiver_expires=None,
            last_cached=date(2019, 12, 1),
        )
        membership.save()
        participant = factories.ParticipantFactory.create(membership=membership)
        make_last_updated_on(participant, date(1995, 1, 1))  # Override default of 'now'

        self.assertEqual(len(cleanup.lapsed_participants()), 0)

    @freeze_time("Tue, 31 Dec 2019 23:59:00 EST")
    def test_waiver_current(self):
        """MITOCers aren't lapsed if they have a waiver, even with dated profile."""
        membership = models.Membership(
            waiver_expires=date(2020, 1, 1),
            membership_expires=None,
            last_cached=date(2019, 12, 1),
        )
        membership.save()
        participant = factories.ParticipantFactory.create(membership=membership)
        make_last_updated_on(participant, date(1995, 1, 1))  # Override default of 'now'

        self.assertEqual(len(cleanup.lapsed_participants()), 0)

    @freeze_time("Tue, 31 Dec 2019 23:59:00 EST")
    def test_recently_participated(self):
        """MITOCers aren't lapsed if they participated in trips recently."""
        # Participant was on a trip in the last year
        trip = factories.TripFactory.create(trip_date=date(2019, 2, 28))
        signup = factories.SignUpFactory.create(
            participant__membership=None, trip=trip, on_trip=True
        )
        # Override default of 'now'
        make_last_updated_on(signup.participant, date(1995, 1, 1))

        self.assertEqual(len(cleanup.lapsed_participants()), 0)

        # However, if the trip was too far in the past, we consider them lapsed
        trip.trip_date = date(2018, 11, 12)  # Over 1 year ago
        trip.save()
        self.assertEqual(cleanup.lapsed_participants().get(), signup.participant)

    @freeze_time("Tue, 31 Dec 2019 23:59:00 EST")
    def test_lapsed(self):
        """Participants are lapsed with expired membership, waiver, and dated profile."""
        membership = models.Membership(
            membership_expires=date(2019, 12, 30),
            waiver_expires=date(2019, 12, 30),
            last_cached=date(2019, 12, 30),
        )
        membership.save()
        participant = factories.ParticipantFactory.create(membership=membership)
        # Hasn't updated in 13 months
        make_last_updated_on(participant, date(2012, 12, 1))

        self.assertEqual(cleanup.lapsed_participants().get(), participant)
