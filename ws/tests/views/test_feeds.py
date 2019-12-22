from bs4 import BeautifulSoup
from freezegun import freeze_time

from ws.tests import TestCase, factories


@freeze_time("Wed, 1 Jan 2020 12:25:00 EST")
class UpcomingTripsViewTest(TestCase):
    def test_success(self):
        # Create a past trip, which will be excluded
        factories.TripFactory.create(trip_date='2019-12-10')
        factories.TripFactory.create(
            trip_date='2020-02-10',
            name='February 10 trip',
            description='A February hike',
        )
        mar_trip = factories.TripFactory.create(
            trip_date='2020-03-15',
            name='March 15 trip',
            description='A hike taking place in March',
            creator=factories.ParticipantFactory.create(name='Suzy Queue'),
        )
        response = self.client.get('/trips.rss')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'xml')

        self.assertEqual(soup.channel.title.string, 'MITOC Trips')
        self.assertEqual(soup.channel.link.string, 'http://example.com/trips/')

        # The two trips appear as items, in reverse chronological order
        march, february = list(soup.channel.find_all('item'))
        self.assertEqual(march.title.string, 'March 15 trip')
        self.assertEqual(february.title.string, 'February 10 trip')

        self.assertEqual(march.guid.string, f'http://example.com/trips/{mar_trip.pk}/')
        self.assertEqual(march.creator.string, 'Suzy Queue')
        self.assertEqual(march.description.string, 'A hike taking place in March')
        self.assertEqual(march.pubDate.string, 'Wed, 01 Jan 2020 12:25:00 -0500')
