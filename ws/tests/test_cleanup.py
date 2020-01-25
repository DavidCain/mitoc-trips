from datetime import date, timedelta
from unittest import mock

from freezegun import freeze_time

from ws import cleanup, models, settings
from ws.tests import TestCase, factories


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


class PurgeNonStudentDiscountsTests(TestCase):
    def setUp(self):
        self.discount_for_everybody = factories.DiscountFactory.create(
            student_required=False
        )
        self.student_only_discount = factories.DiscountFactory.create(
            student_required=True
        )

    def test_purged(self):
        # Create a collection of participants with every student affiliation
        current_students = [
            factories.ParticipantFactory.create(affiliation='MU'),
            factories.ParticipantFactory.create(affiliation='MG'),
            factories.ParticipantFactory.create(affiliation='NU'),
            factories.ParticipantFactory.create(affiliation='NG'),
        ]
        alum = factories.ParticipantFactory.create(affiliation='MU')
        former_undergrad = factories.ParticipantFactory.create(affiliation='MU')
        former_grad_student = factories.ParticipantFactory.create(affiliation='NG')

        # Assign both discounts to everybody, since they're all currently students
        everybody = [former_undergrad, former_grad_student, alum, *current_students]
        for participant in everybody:
            participant.discounts.set(
                [self.discount_for_everybody, self.student_only_discount]
            )

        # The former students move into non-student statuses
        alum.affiliation = 'ML'
        alum.save()
        former_undergrad.affiliation = 'MA'
        former_undergrad.save()
        former_grad_student.affiliation = 'NA'
        former_grad_student.save()

        cleanup.purge_non_student_discounts()

        # All participants remain in the discount which has no student requirement
        self.assertCountEqual(
            self.discount_for_everybody.participant_set.all(), everybody
        )

        # Just the students keep the student discount!
        self.assertCountEqual(
            self.student_only_discount.participant_set.all(), current_students
        )


class PurgeMedicalInfoTests(TestCase):
    def test_current_participants_unaffected(self):
        # Will automatically get a profile_last_updated value
        participant = factories.ParticipantFactory.create()
        original = participant.emergency_info
        with mock.patch.object(cleanup.logger, 'info') as log_info:
            cleanup.purge_old_medical_data()
        log_info.assert_not_called()  # Nothing to log, no changes made
        participant.emergency_info.refresh_from_db()
        self.assertEqual(original, participant.emergency_info)

    def test_purge_medical_data(self):
        # (Will have medical information created)
        participant = factories.ParticipantFactory.create(
            membership=None, name='Old Member', email='old@example.com', pk=823
        )
        # Hasn't updated in at least 13 months
        make_last_updated_on(participant, date(2012, 12, 1))

        # Note that we started with information
        e_info = participant.emergency_info
        e_contact = e_info.emergency_contact
        self.assertTrue(e_info.allergies)
        self.assertTrue(e_info.medications)
        self.assertTrue(e_info.medical_history)

        with mock.patch.object(cleanup.logger, 'info') as log_info:
            cleanup.purge_old_medical_data()
        log_info.assert_called_once_with(
            'Purging medical data for %s (%s - %s, last updated %s)',
            'Old Member',
            823,
            'old@example.com',
            date(2012, 12, 1),
        )

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
