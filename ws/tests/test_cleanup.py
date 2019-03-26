from datetime import date, timedelta

from django.test import TransactionTestCase
from freezegun import freeze_time

from ws import cleanup, models, settings
from ws.tests import factories


def make_last_updated_on(participant, some_date):
    """ Update the `profile_last_updated` field to be on some given date.

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


class LapsedTests(TransactionTestCase):
    @freeze_time("Wed, 25 Dec 2019 12:00:00 EST")
    def test_not_lapsed_with_recent_update(self):
        today = date(2019, 12, 25)
        still_within_window = today - timedelta(
            days=settings.MUST_UPDATE_AFTER_DAYS - 1
        )
        factories.ParticipantFactory.create(profile_last_updated=still_within_window)

        self.assertEqual(len(cleanup.lapsed_participants()), 0)

    @freeze_time("Tue, 31 Dec 2019 23:59:00 EST")
    def test_membership_current(self):
        """ Members aren't lapsed if they have a membership, even with dated profile. """
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
        """ Members aren't lapsed if they have a waiver, even with dated profile. """
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
        """ Members aren't lapsed if they participated in trips recently. """
        # Participant was on a trip in the last year
        trip = factories.TripFactory.create(trip_date=date(2019, 2, 28))
        signup = factories.SignUpFactory.create(trip=trip, on_trip=True)
        # Override default of 'now'
        make_last_updated_on(signup.participant, date(1995, 1, 1))

        self.assertEqual(len(cleanup.lapsed_participants()), 0)

        # However, if the trip was too far in the past, we consider them lapsed
        trip.trip_date = date(2018, 11, 12)  # Over 1 year ago
        trip.save()
        self.assertEqual(cleanup.lapsed_participants().get(), signup.participant)

    @freeze_time("Tue, 31 Dec 2019 23:59:00 EST")
    def test_lapsed(self):
        """ Participants are lapsed with expired membership, waiver, and dated profile. """
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


class PurgeMedicalInfoTests(TransactionTestCase):
    def test_current_participants_unaffected(self):
        # Will automatically get a profile_last_updated value
        participant = factories.ParticipantFactory.create()
        original = participant.emergency_info
        cleanup.purge_old_medical_data()
        participant.emergency_info.refresh_from_db()
        self.assertEqual(original, participant.emergency_info)

    def test_purge_medical_data(self):
        # Gets medical info for free!
        participant = factories.ParticipantFactory.create(membership=None)
        # Hasn't updated in 13 months
        make_last_updated_on(participant, date(2012, 12, 1))

        # Note that we started with information
        e_info = participant.emergency_info
        e_contact = e_info.emergency_contact
        self.assertNotEqual(e_info.allergies, '')
        self.assertNotEqual(e_info.medications, '')
        self.assertNotEqual(e_info.medical_history, '')

        cleanup.purge_old_medical_data()

        # Re-query so that we get all fresh data (refresh_from_db only does one model)
        participant = models.Participant.objects.select_related(
            'emergency_info__emergency_contact'
        ).get(pk=participant.pk)

        # Now, note that sensitive fields have been cleaned out
        self.assertEqual(participant.emergency_info.allergies, '')
        self.assertEqual(participant.emergency_info.medications, '')
        self.assertEqual(participant.emergency_info.medical_history, '')

        # The emergency contact remains, though.
        self.assertEqual(participant.emergency_info.emergency_contact, e_contact)
