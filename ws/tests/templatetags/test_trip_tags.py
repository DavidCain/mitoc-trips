from datetime import date

from bs4 import BeautifulSoup
from django.template import Context, Template
from freezegun import freeze_time

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
