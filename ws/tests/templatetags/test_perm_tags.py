from datetime import date

from django.contrib.auth.models import Group, User
from django.template import Context, Template
from freezegun import freeze_time

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
        admin = User.objects.create_superuser('admin', 'admin@example.com', '1234')
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
