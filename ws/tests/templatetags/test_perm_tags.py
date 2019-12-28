from datetime import date

from django.contrib.auth.models import Group
from django.template import Context, Template
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums
from ws.tests import TestCase, factories


class IsTheWimpTest(TestCase):
    @staticmethod
    def _is_wimp(user, participant):
        html_template = Template(
            '{% load perm_tags %}{% if user|is_the_wimp:par %}WIMP!{% endif %}'
        )
        context = Context({'user': user, 'par': participant})
        return html_template.render(context) == 'WIMP!'

    def test_winter_school_wimp(self):
        user = factories.UserFactory.create()
        wimp_group, _created = Group.objects.get_or_create(name='WIMP')
        wimp_group.user_set.add(user)
        self.assertTrue(self._is_wimp(user, None))

    def test_admin_considered_wimp(self):
        admin = factories.UserFactory.create(is_superuser=True)
        self.assertTrue(self._is_wimp(admin, None))

    def test_user_without_participant(self):
        user = factories.UserFactory.create()
        self.assertFalse(self._is_wimp(user, None))

    def test_only_upcoming_trips_as_wimp(self):
        participant = factories.ParticipantFactory.create()
        user = participant.user
        self.assertFalse(self._is_wimp(user, participant))

        other_par = factories.ParticipantFactory.create()
        with freeze_time("2020-01-15 14:56:00 EST"):
            # No trips assigned to this participant - not the WIMP
            factories.TripFactory.create(trip_date=date(2020, 1, 20), wimp=other_par)
            self.assertFalse(self._is_wimp(user, participant))

            # One upcoming trip - counts as WIMP!
            factories.TripFactory.create(trip_date=date(2020, 1, 20), wimp=participant)
            self.assertTrue(self._is_wimp(user, participant))

        # Night of the trip - still counts as WIMP!
        with freeze_time("2020-01-20 23:56:00 EST"):
            self.assertTrue(self._is_wimp(user, participant))

        # Afterwards, no longer considered WIMP.
        # (can still view medical page, though information becomes redacted after time passes)
        with freeze_time("2020-01-21 09:00:00 EST"):
            self.assertFalse(self._is_wimp(user, participant))


class ChairActivitiesTest(TestCase):
    @staticmethod
    def _chair_activities(user, allow_superusers=None):
        body = 'user|chair_activities'
        if allow_superusers is not None:
            body = f'{body}:{bool(allow_superusers)}'

        html_template = Template(
            '{% load perm_tags %}'
            '{% for activity_enum in ' + body + ' %}'
            '{{ activity_enum.label }}{% if not forloop.last %}\n{% endif %}'
            '{% endfor %}'
        )
        context = Context({'user': user})
        lines = html_template.render(context)
        return lines.split('\n') if lines else []

    def test_not_chair(self):
        normal_user = factories.UserFactory.create()
        self.assertEqual(self._chair_activities(normal_user), [])

    def test_activity_chair(self):
        user = factories.UserFactory.create()
        perm_utils.make_chair(user, enums.Activity.CLIMBING)
        self.assertEqual(self._chair_activities(user), ['Climbing'])

    def test_superuser(self):
        """ An optional flag indicates if superusers should be considered chairs. """
        admin = factories.UserFactory.create(is_superuser=True)

        # True is useful for granting admins access to activity functions
        self.assertEqual(
            self._chair_activities(admin, allow_superusers=True),
            ['Biking', 'Boating', 'Cabin', 'Climbing', 'Hiking', 'Winter School'],
        )
        # False is useful for rendering actual chairships held
        self.assertEqual(self._chair_activities(admin, allow_superusers=False), [])

        # We can still report chairships held
        perm_utils.make_chair(admin, enums.Activity.WINTER_SCHOOL)
        self.assertEqual(
            self._chair_activities(admin, allow_superusers=False), ['Winter School']
        )
