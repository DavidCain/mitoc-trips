from datetime import date

from bs4 import BeautifulSoup
from django.template import Context, Template
from freezegun import freeze_time

from ws import enums, models
from ws.tests import TestCase, factories


class TripTagsTest(TestCase):
    @freeze_time("Jan 11 2019 20:30:00 EST")
    def test_simple_trip_list(self):
        trips = [
            factories.TripFactory.create(name="Past Trip", trip_date=date(2017, 8, 2)),
            factories.TripFactory.create(name="Today!", trip_date=date(2019, 1, 11)),
            factories.TripFactory.create(name="Soon Trip", trip_date=date(2019, 1, 16)),
            factories.TripFactory.create(
                name="Later Trip", trip_date=date(2019, 1, 19)
            ),
        ]
        html_template = Template('{% load trip_tags %}{% simple_trip_list trips %}')
        context = Context({'trips': trips})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')
        table = soup.find('table')
        heading = table.find('thead').find_all('th')
        self.assertEqual([tr.text for tr in heading], ['Trip', 'Date', 'Leaders'])

        rows = [tr.find_all('td') for tr in table.find('tbody').find_all('tr')]

        date_per_trip = [
            (trip.find('a').text, rendered_date.text.strip())
            for (trip, rendered_date, _leaders) in rows
        ]
        # We render the dates for each trip unambiguously
        self.assertEqual(
            date_per_trip,
            [
                ('Past Trip', '2017-08-02'),
                ('Today!', 'Today'),
                ('Soon Trip', 'Wed'),
                ('Later Trip', 'Jan 19'),
            ],
        )

    @freeze_time("Jan 10 2019 20:30:00 EST")
    def test_trip_list_approve_mode(self):
        def _ws_trip(trip_date, **kwargs):
            return factories.TripFactory.create(
                program=enums.Program.WINTER_SCHOOL.value,
                trip_date=trip_date,
                **kwargs,
            )

        has_itinerary = _ws_trip(
            date(2019, 1, 11), info=factories.TripInfoFactory.create()
        )
        no_itinerary1 = _ws_trip(date(2019, 1, 11))
        no_itinerary2 = _ws_trip(date(2019, 1, 11))

        html_template = Template('{% load trip_tags %}{% trip_list_table trips True %}')
        context = Context({'trips': models.Trip.objects.all().order_by('pk')})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')

        table = soup.find('table')
        heading = table.find('thead').find_all('th')
        self.assertEqual(
            [tr.text for tr in heading],
            ['Name', 'Date', 'Description', 'Leaders', 'Approve'],
        )

        rows = [tr.find_all('td') for tr in table.find('tbody').find_all('tr')]
        trip_info = [
            {
                'link': row[0].find('a').attrs['href'],
                'icon_classes': row[0].find('i', class_='fas').attrs['class'],
            }
            for row in rows
        ]

        # For each trip, we give a link to the approve page
        # We also include an icon indicating if the trip has an itinerary or not
        self.assertEqual(
            trip_info,
            [
                {
                    'link': f'/winter_school/trips/{has_itinerary.pk}/',
                    'icon_classes': ['fas', 'fa-fw', 'fa-check', 'text-success'],
                },
                {
                    'link': f'/winter_school/trips/{no_itinerary1.pk}/',
                    'icon_classes': [
                        'fas',
                        'fa-fw',
                        'fa-exclamation-triangle',
                        'text-danger',
                    ],
                },
                {
                    'link': f'/winter_school/trips/{no_itinerary2.pk}/',
                    'icon_classes': [
                        'fas',
                        'fa-fw',
                        'fa-exclamation-triangle',
                        'text-danger',
                    ],
                },
            ],
        )
