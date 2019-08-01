import re

from bs4 import BeautifulSoup
from freezegun import freeze_time

from ws.tests import TestCase, factories

WHITESPACE = re.compile(r'\s+')


def strip_whitespace(text):
    return re.sub(WHITESPACE, ' ', text).strip()


class Helpers:
    def _get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        return response, soup

    def _expect_title(self, soup, expected):
        title = strip_whitespace(soup.title.string)
        self.assertEqual(title, f'{expected} | MITOC Trips')

    def _expect_past_trips(self, response, expected_trip_pks):
        self.assertEqual(
            [trip.pk for trip in response.context['past_trips']], expected_trip_pks
        )

    def _expect_current_trips(self, response, expected_trip_pks):
        self.assertEqual(
            [trip.pk for trip in response.context['current_trips']], expected_trip_pks
        )

    def _expect_upcoming_header(self, soup, expected_text):
        """ Expect a text label on the header, plus the subscribe button. """
        header = soup.body.find('h3')
        header_text = strip_whitespace(header.get_text())
        # There is a 'Subscribe' button included in the header
        self.assertEqual(header_text, f'{expected_text} Subscribe')

    def _expect_link_for_date(self, soup, datestring):
        link = soup.find('a', href=f'/trips/?after={datestring}')
        self.assertEqual(link.get_text(strip=True), 'Previous trips')


@freeze_time("2019-02-15 12:25:00 EST")
class UpcomingTripsViewTest(TestCase, Helpers):
    def test_upcoming_trips_without_filter(self):
        """ With no default filter, we only show upcoming trips. """
        response, soup = self._get('/trips/')
        # We don't bother rendering any past trips
        self.assertNotIn('past_trips', response.context)
        self._expect_title(soup, 'Upcoming trips')
        # We just say 'Upcoming trips' (no mention of date)
        self._expect_upcoming_header(soup, 'Upcoming trips')

    def test_invalid_filter(self):
        """ When an invalid date is passed, we just ignore it. """
        # Make two trips that are in the future, but before the requested cutoff
        factories.TripFactory.create(trip_date='2019-02-28')
        factories.TripFactory.create(trip_date='2019-02-27')

        # Ask for upcoming trips after an invalid future date
        response, soup = self._get('/trips/?after=2019-02-31')

        # We warn the user that this date was invalid.
        warning = soup.find(class_='alert alert-danger')
        self.assertTrue(response.context['date_invalid'])
        self.assertIn('Invalid date', warning.get_text())

        # However, we still return results (behaving as if no date filter was given)
        # We don't include past trips, though, since the `after` cutoff was invalid
        # (We only show upcoming trips)
        self._expect_title(soup, 'Upcoming trips')
        self.assertNotIn('past_trips', response.context)
        # We use today's date for the 'previous trips' link
        self._expect_link_for_date(soup, '2018-02-15')

    def test_trips_with_filter(self):
        """ We support filtering the responded list of trips. """
        # Make a very old trip that will not be in our filter
        factories.TripFactory.create(trip_date='2016-12-23')

        # Make an older trip, that takes place after our query
        expected_trip = factories.TripFactory.create(trip_date='2017-11-21')

        # Filter based on a date in the past
        response, soup = self._get('/trips/?after=2017-11-15')
        self.assertFalse(response.context['date_invalid'])

        # Observe that we have an 'Upcoming trips' section, plus a section for past trips
        self._expect_upcoming_header(soup, 'Upcoming trips')
        self._expect_title(soup, 'Trips after 2017-11-15')
        self._expect_past_trips(response, [expected_trip.pk])
        self._expect_link_for_date(soup, '2016-11-15')

    def test_upcoming_trips_can_be_filtered(self):
        """ If supplying an 'after' date in the future, that still permits filtering! """
        _next_week = factories.TripFactory.create(trip_date='2019-02-22')
        next_month = factories.TripFactory.create(trip_date='2019-03-22')
        response, soup = self._get('/trips/?after=2019-03-15')
        self._expect_link_for_date(soup, '2018-03-15')
        self._expect_upcoming_header(soup, 'Trips after Mar 15, 2019')
        # The trip next month is included, but not next week (since we're filtering ahead)
        self._expect_current_trips(response, [next_month.pk])


@freeze_time("2019-02-15 12:25:00 EST")
class AllTripsViewTest(TestCase, Helpers):
    def test_all_trips_with_no_past(self):
        """ Even with no past trips, we still display 'All trips' """
        response, soup = self._get('/trips/all/')
        self.assertFalse(response.context['past_trips'])
        self._expect_title(soup, 'All trips')

    def test_all_trips_with_past_trips(self):
        """ Test the usual case - 'all trips' segmenting past & upcoming trips. """
        next_week = factories.TripFactory.create(trip_date='2019-02-22')
        last_month = factories.TripFactory.create(trip_date='2019-01-15')
        years_ago = factories.TripFactory.create(trip_date='2010-11-15')
        response, soup = self._get('/trips/all/')
        self._expect_title(soup, 'All trips')
        self._expect_current_trips(response, [next_week.pk])
        self._expect_past_trips(response, [last_month.pk, years_ago.pk])

    def test_all_trips_with_filter(self):
        """ We support filtering trips even on the 'all' page.

        The default interaction with filtering trips should instead just use
        the `/trips/` URL, but this test demonstrates that filtering works on
        the 'all' page too.
        """
        # Make a very old trip that will not be in our filter
        factories.TripFactory.create(trip_date='2016-12-23')

        # Make an older trip, that takes place after our query
        expected_trip = factories.TripFactory.create(trip_date='2017-11-21')
        response, soup = self._get('/trips/all/?after=2017-11-15')
        self._expect_title(soup, 'Trips after 2017-11-15')
        self._expect_past_trips(response, [expected_trip.pk])
        self._expect_link_for_date(soup, '2016-11-15')
