from datetime import date, datetime

from django.template import Context, Template
from freezegun import freeze_time

from ws import models
from ws.templatetags.trip_tags import annotated_for_trip_list  # TODO: Move.
from ws.tests import TestCase, factories
from ws.utils.dates import localize


@freeze_time("11 Dec 2025 12:00:00 EST")
class EmailTagsTests(TestCase):
    def _make_trip(self):
        trip = factories.TripFactory.create(
            name="Some Cool Upcoming Trip",
            trip_date=date(2025, 12, 14),
            difficulty_rating='Advanced',
            prereqs='Comfort with rough terrain',
            signups_open_at=localize(datetime(2025, 12, 10, 12, 0)),
            signups_close_at=localize(datetime(2025, 12, 13, 21, 30)),
            algorithm='fcfs',
        )
        return annotated_for_trip_list(models.Trip.objects.filter(pk=trip.pk)).first()

    def test_text_template(self):
        """ Test the textual template (used for clients that prefer not to use HTML). """
        trip = self._make_trip()
        txt_template = Template(
            '{% load email_tags %}{% upcoming_trip_summary_txt trip %}'
        )
        rendered_txt = txt_template.render(Context({'trip': trip}))
        expected_txt = '\n'.join(
            [
                'Some Cool Upcoming Trip',
                '=======================',
                f'<https://mitoc-trips.mit.edu/trips/{trip.pk}/>',
                'Sunday, December 14',
                'Difficulty rating: Advanced',
                'Prerequisites: Comfort with rough terrain',
                'Spaces remaining: 8',
                'Signups close at: Dec. 13, 2025, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
            ]
        )
        self.assertEqual(rendered_txt, expected_txt)

    def test_html_template(self):
        """ Test the HTML generation (for most email clients) """
        trip = self._make_trip()
        html_template = Template(
            '{% load email_tags %}{% upcoming_trip_summary_html trip %}'
        )
        url = f'https://mitoc-trips.mit.edu/trips/{trip.pk}/'
        rendered_html = html_template.render(Context({'trip': trip}))
        expected_html = '\n'.join(
            [
                f'<h2><a href="{url}">Some Cool Upcoming Trip</a></h2>',
                '<h3>Sunday, December 14</h3>',
                '<p>',
                '  <ul>',
                '    <li><strong>Difficulty rating:</strong> Advanced</li>',
                '      <li><strong>Prerequisites:</strong> Comfort with rough terrain</li>',
                '      <li><strong>Spaces remaining:</strong> 8</li>',
                '      <li><strong>Signups close at:</strong> Dec. 13, 2025, 9:30 p.m.</li>',
                '    <li><strong>Algorithm:</strong> first-come, first-serve</li>',
                '  </ul>',
                '</p>',
                '',
            ]
        )
        self.assertEqual(rendered_html, expected_html)
