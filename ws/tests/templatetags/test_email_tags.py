from datetime import date, datetime

from django.template import Context, Template
from django.test import TestCase
from freezegun import freeze_time

from ws import enums, models
from ws.templatetags.trip_tags import annotated_for_trip_list  # TODO: Move.
from ws.tests import factories
from ws.utils.dates import localize


@freeze_time("11 Dec 2025 12:00:00 EST")
class EmailTagsTests(TestCase):
    @staticmethod
    def _make_trip(**overrides):
        trip_kwargs = {
            'name': "Some Cool Upcoming Trip",
            'program': enums.Program.WINTER_NON_IAP.value,
            'trip_type': enums.TripType.HIKING.value,
            'winter_terrain_level': 'C',
            'trip_date': date(2025, 12, 14),
            'difficulty_rating': 'Advanced',
            'prereqs': 'Comfort with rough terrain',
            'signups_open_at': localize(datetime(2025, 12, 10, 12, 0)),
            'signups_close_at': localize(datetime(2025, 12, 13, 21, 30)),
            'algorithm': 'fcfs',
            **overrides,
        }
        trip = factories.TripFactory.create(**trip_kwargs)
        return annotated_for_trip_list(models.Trip.objects.filter(pk=trip.pk)).get()

    def test_text_template_no_program(self):
        """We exclude the program 'None.'"""
        trip = self._make_trip(trip_type=enums.TripType.NONE.value)
        txt_template = Template(
            '{% load email_tags %}{% upcoming_trip_summary_txt trip %}'
        )
        rendered_txt = txt_template.render(Context({'trip': trip}))
        self.assertNotIn('Type: None', rendered_txt.split('\n'))
        expected_txt = '\n'.join(
            [
                'Some Cool Upcoming Trip',
                '=======================',
                f'<https://mitoc-trips.mit.edu/trips/{trip.pk}/>',
                'Sunday, December 14',
                'Program: Winter (outside IAP)',
                #'Type: None',  # Omitted because it's not terribly helpful.
                'Terrain level: C',
                'Difficulty rating: Advanced',
                'Prerequisites: Comfort with rough terrain',
                'Spaces remaining: 8',
                'Signups close at: Dec. 13, 2025, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
            ]
        )
        self.assertEqual(rendered_txt, expected_txt)

    def test_text_template_no_trip_type(self):
        """We exclude the trip type 'None.'"""
        trip = self._make_trip(
            program=enums.Program.NONE.value,
            trip_type=enums.TripType.OTHER.value,
            winter_terrain_level=None,
        )
        txt_template = Template(
            '{% load email_tags %}{% upcoming_trip_summary_txt trip %}'
        )
        rendered_txt = txt_template.render(Context({'trip': trip}))
        self.assertNotIn('Program: None', rendered_txt.split('\n'))
        expected_txt = '\n'.join(
            [
                'Some Cool Upcoming Trip',
                '=======================',
                f'<https://mitoc-trips.mit.edu/trips/{trip.pk}/>',
                'Sunday, December 14',
                #'Program: None',  # Omitted because it's not terribly helpful.
                'Type: Other',
                # 'Terrain level: ...',  # Omitted because this isn't a WS trip.
                'Difficulty rating: Advanced',
                'Prerequisites: Comfort with rough terrain',
                'Spaces remaining: 8',
                'Signups close at: Dec. 13, 2025, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
            ]
        )
        self.assertEqual(rendered_txt, expected_txt)

    def test_text_template(self):
        """Test the textual template (used for clients that prefer not to use HTML)."""
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
                'Program: Winter (outside IAP)',
                'Type: Hiking',
                'Terrain level: C',
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
        """Test the HTML generation (for most email clients)"""
        trip = self._make_trip()
        html_template = Template(
            '{% load email_tags %}{% upcoming_trip_summary_html trip %}'
        )
        url = f'https://mitoc-trips.mit.edu/trips/{trip.pk}/'
        rendered_html = html_template.render(Context({'trip': trip}))

        inline = {
            'a': 'color: #3498db; text-decoration: underline;',
            'p': 'font-family: sans-serif; font-size: 14px; font-weight: normal; margin: 0; margin-bottom: 15px;',
            'h2': 'color: #000000; font-family: sans-serif; font-weight: 400; line-height: 1.4; margin: 0;',
            'h3': 'color: #000000; font-family: sans-serif; font-weight: 400; line-height: 1.4; margin: 0;',
            'ul': 'font-family: sans-serif; font-size: 14px; font-weight: normal; margin: 0; margin-bottom: 15px;',
            'li': 'list-style-position: inside; margin-left: 5px;',
        }

        expected_html = '\n'.join(
            # pylint: disable=f-string-without-interpolation
            [
                f'<h2 style="{inline["h2"]}">',
                f'  <a href="{url}" style="{inline["a"]}">Some Cool Upcoming Trip</a>',
                f'</h2>',
                f'<h3 style="{inline["h3"]}">Sunday, December 14</h3>',
                f'<p style="{inline["p"]}">',
                f'  <ul style="{inline["ul"]}">',
                f'      <li style="{inline["li"]}"><strong>Program</strong>: Winter (outside IAP)',
                f'      </li>',
                f'      <li style="{inline["li"]}"><strong>Type</strong>: Hiking</li>',
                f'      <li style="{inline["li"]}"><strong>Terrain level</strong>: C</li>',
                f'    <li style="{inline["li"]}"><strong>Difficulty rating:</strong> Advanced</li>',
                f'      <li style="{inline["li"]}"><strong>Prerequisites:</strong> Comfort with rough terrain</li>',
                f'      <li style="{inline["li"]}"><strong>Spaces remaining:</strong> 8</li>',
                f'      <li style="{inline["li"]}"><strong>Signups close at:</strong> Dec. 13, 2025, 9:30 p.m.</li>',
                f'    <li style="{inline["li"]}"><strong>Algorithm:</strong> first-come, first-serve</li>',
                '  </ul>',
                '</p>',
                '',
            ]
        )
        self.assertEqual(rendered_html, expected_html)
