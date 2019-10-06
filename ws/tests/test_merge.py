import unittest
from datetime import datetime

import pytz
from django.contrib.auth.models import Permission, User
from django.db import connections
from django.db.utils import IntegrityError
from mitoc_const import affiliations

from ws import merge, models
from ws.tests import TestCase, factories


# TODO (mypy): If/when using type checking, just get rid of this
class ExpectationsTypeTest(unittest.TestCase):
    def _assert_table_to_col_tuple(self, expectations):
        self.assertTrue(isinstance(expectations, dict))
        self.assertTrue(all(isinstance(cols, tuple) for cols in expectations.values()))

    def test_expectations(self):
        """Basic type checking to guard against silly typos."""
        self._assert_table_to_col_tuple(merge.EXPECTED_USER_TABLES)
        self._assert_table_to_col_tuple(merge.EXPECTED_PARTICIPANT_TABLES)


class MergeUtilTest(TestCase):
    def test_check_fk_tables_missing_fk(self):
        cursor = connections['default'].cursor()
        expected = {
            'auth_user_user_permissions': 'user_id',
            'auth_user_groups': 'user_id',
            'account_emailaddress': 'user_id',
            # 'django_admin_log': 'user_id',
            'ws_participant': 'user_id',
            'ws_mailinglistrequest': ('requested_by_id',),
        }
        with self.assertRaises(ValueError) as err:
            merge.check_fk_tables(
                cursor, src_table='auth_user', column='id', expected=expected
            )

        self.assertEqual(
            str(err.exception),
            'Database has more FKs. Not handled: django_admin_log.user_id',
        )

    def test_simple_fk_update(self):
        """We can directly modify any rows that have FK constraints (without unique constraints)"""
        cursor = connections['default'].cursor()

        # Make Two users - we'll transfer the email address from one to the other
        user = factories.UserFactory.create(email='primary@example.com')
        other = factories.UserFactory.create(email='other@example.com')
        other.emailaddress_set.update(primary=False)  # (allows the move)

        # Move the secondary email address for the other user to our user
        merge.simple_fk_update(
            cursor, 'account_emailaddress', 'user_id', other.pk, user.pk
        )
        self.assertCountEqual(
            [email_addr.email for email_addr in user.emailaddress_set.all()],
            ['primary@example.com', 'other@example.com'],
        )


class MergeTest(TestCase):
    def setUp(self):
        super().setUp()
        self.old = factories.ParticipantFactory.create(
            email='tim@mit.edu', affiliation=affiliations.MIT_UNDERGRAD.CODE
        )
        self.tim = factories.ParticipantFactory.create(
            email='tim@alum.mit.edu', affiliation=affiliations.MIT_ALUM.CODE
        )

    def _migrate(self):
        merge.merge_participants(self.old, self.tim)
        self.tim.refresh_from_db()

    def _assert_email_handling(self):
        """Tim retains his primary email address, but also gains his old MIT address!"""
        self.assertEqual(self.tim.email, 'tim@alum.mit.edu')
        emails = {addr.email: addr for addr in self.tim.user.emailaddress_set.all()}
        self.assertCountEqual(emails, {'tim@mit.edu', 'tim@alum.mit.edu'})
        self.assertFalse(emails['tim@mit.edu'].primary)
        self.assertTrue(emails['tim@alum.mit.edu'].primary)
        self.assertEqual(emails['tim@mit.edu'].user_id, self.tim.user_id)
        self.assertEqual(emails['tim@alum.mit.edu'].user_id, self.tim.user_id)

    def _assert_user_handling(self):
        """Tim's old user is removed, but his groups & emails are preserved."""
        self.assertFalse(User.objects.filter(pk=self.old.user_id))

    def test_migrate_participant(self):
        """Test the usual case of migrating a normal participant."""
        self._migrate()

        self._assert_email_handling()
        self._assert_user_handling()

    def test_old_lotteryinfo_removed(self):
        """When the new participant has an up-to-date lottery info, we use that."""
        old_info = factories.LotteryInfoFactory.create(participant=self.old)
        new_info = factories.LotteryInfoFactory.create(participant=self.tim)
        self._migrate()

        new_info.refresh_from_db()  # Still exists! We did not alter.
        with self.assertRaises(models.LotteryInfo.DoesNotExist):
            old_info.refresh_from_db()

    def test_old_lotteryinfo_migrated(self):
        """When only the old participant had lottery info, we migrate that."""
        old_info = factories.LotteryInfoFactory.create(participant=self.old)
        self._migrate()

        old_info.refresh_from_db()
        self.assertEqual(old_info.participant, self.tim)

    def test_permissions_not_handled(self):
        """We don't make use of permissions, so we don't attempt to migrate."""
        permission = Permission.objects.first()  # Doesn't matter what for.
        self.assertIsNotNone(permission)
        self.old.user.user_permissions.add(permission)
        with self.assertRaises(ValueError):
            self._migrate()

        self.old.refresh_from_db()  # Still exists! We rolled back.

    def test_feedback_migrated(self):
        """This is an example of a model with two separate FK's to the participant table."""
        feedback_as_participant = factories.FeedbackFactory.create(participant=self.old)
        feedback_as_leader = factories.FeedbackFactory.create(leader=self.old)

        self._migrate()
        feedback_as_participant.refresh_from_db()
        feedback_as_leader.refresh_from_db()
        self.assertEqual(feedback_as_participant.participant.pk, self.tim.pk)
        self.assertEqual(feedback_as_leader.leader, self.tim)

    def test_password_quality(self):
        """Only password quality from the newer participant is kept."""
        factories.PasswordQualityFactory.create(participant=self.old, is_insecure=True)
        factories.PasswordQualityFactory.create(participant=self.tim, is_insecure=False)
        self._migrate()
        self.assertFalse(self.tim.passwordquality.is_insecure)

    def test_membership_reminders(self):
        """The newest reminder is honored, even if delivered to the older participant."""
        newer_reminder_sent_at = datetime(2020, 12, 25, tzinfo=pytz.UTC)
        factories.MembershipReminderFactory.create(
            participant=self.tim,
            reminder_sent_at=datetime(2020, 10, 1, tzinfo=pytz.UTC),
        )
        factories.MembershipReminderFactory.create(
            participant=self.old,
            reminder_sent_at=newer_reminder_sent_at,
        )

        self._migrate()
        reminder = models.MembershipReminder.objects.get(participant=self.tim)
        self.assertEqual(reminder.reminder_sent_at, newer_reminder_sent_at)

    def test_conflicts(self):
        """We cannot merge participants who are clearly different people."""
        trip = factories.TripFactory.create()

        # Each participant can have at most one signup per trip!
        factories.SignUpFactory.create(participant=self.old, trip=trip)
        factories.SignUpFactory.create(participant=self.tim, trip=trip)
        with self.assertRaises(IntegrityError):
            self._migrate()

        self.old.refresh_from_db()  # Still exists! We rolled back.
