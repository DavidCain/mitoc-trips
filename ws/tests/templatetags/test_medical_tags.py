from datetime import date

from bs4 import BeautifulSoup
from django.template import Context, Template
from freezegun import freeze_time

from ws.tests import TestCase, factories, strip_whitespace


class ShowWimpTagsTests(TestCase):
    def test_information_displayed(self):
        wimp = factories.ParticipantFactory.create(
            cell_phone='+13395551111', email='thewimp@example.com'
        )
        context = Context({'wimp': wimp})
        template_to_render = Template(
            '{% load medical_tags %}{% show_wimp wimp True %}'
        )
        html = template_to_render.render(context)
        soup = BeautifulSoup(html, 'xml')

        # We check that key contact information is shown!
        self.assertTrue(soup.find(string='+13395551111'))
        self.assertTrue(soup.find('a', href='mailto:wimp@mit.edu'))
        self.assertTrue(soup.find('a', href='mailto:thewimp@example.com'))

    def test_wimp_email_hidden(self):
        """The wimp@mit.edu email can be hidden (as in for single trips)."""
        wimp = factories.ParticipantFactory.create(email='thewimp@example.com')
        template_to_render = Template('{% load medical_tags %}{% show_wimp wimp %}')
        soup = BeautifulSoup(template_to_render.render(Context({'wimp': wimp})), 'xml')

        self.assertFalse(soup.find('a', href='mailto:wimp@mit.edu'))
        self.assertTrue(soup.find('a', href='mailto:thewimp@example.com'))


class TripItineraryTest(TestCase):
    def test_no_info(self):
        trip = factories.TripFactory.create(info=None)
        context = Context({'trip': trip})
        template_to_render = Template(
            '{% load medical_tags %}{% trip_itinerary trip %}'
        )
        html = template_to_render.render(context)
        self.assertFalse(html.strip())

    def test_information_displayed(self):
        trip = factories.TripFactory.create(
            info=factories.TripInfoFactory.create(
                start_location="Old Bridle Path trailhead",
                start_time='9 am at the latest',
                worry_time='5 pm',
            ),
        )
        context = Context({'trip': trip})
        template_to_render = Template(
            '{% load medical_tags %}{% trip_itinerary trip %}'
        )
        html = template_to_render.render(context)
        soup = BeautifulSoup(html, 'xml')
        self.assertTrue(soup.find('dd', string="Old Bridle Path trailhead"))
        self.assertTrue(soup.find('dd', string="9 am at the latest"))


class TripInfoTest(TestCase):
    def setUp(self):
        super().setUp()
        self.viewing_participant = factories.ParticipantFactory.create()

    def _render(self, trip, show_participants_if_no_itinerary=False):
        context = Context(
            {
                'trip': trip,
                'viewing_participant': self.viewing_participant,
                'show_participants_if_no_itinerary': show_participants_if_no_itinerary,
            }
        )
        template_to_render = Template(
            '{% load medical_tags %}{% trip_info trip show_participants_if_no_itinerary %}'
        )
        html = template_to_render.render(context)
        soup = BeautifulSoup(html, 'xml')
        return soup

    def test_no_itinerary(self):
        trip = factories.TripFactory.create(info=None)
        soup = self._render(trip)
        danger = soup.find(class_='alert alert-danger')
        self.assertEqual(
            strip_whitespace(danger.text),
            "A detailed trip itinerary has not been submitted for this trip!",
        )

    def test_no_itinerary_but_show_participants(self):
        trip = factories.TripFactory.create(info=None)
        factories.SignUpFactory.create(
            trip=trip,
            on_trip=True,
            participant__name="Car Owner",
            participant__car=factories.CarFactory.create(make="Honda", model="Odyssey"),
        )
        factories.SignUpFactory.create(
            trip=trip,
            on_trip=True,
            participant__name="Car Renter",
            participant__car=factories.CarFactory.create(
                make="Subaru", model="Outback"
            ),
        )
        soup = self._render(trip, show_participants_if_no_itinerary=True)

        # We have a table of all participants
        self.assertTrue(soup.find('h4', string='Participants'))
        self.assertTrue(soup.find('td', string='Car Renter'))
        self.assertTrue(soup.find('td', string='Car Owner'))

        # We show a table of all drivers out of caution
        self.assertTrue(soup.find('h4', string='Drivers'))
        warning = soup.find(class_='alert alert-warning')
        self.assertIn(
            "all trip-goers that submitted car information",
            strip_whitespace(warning.text),
        )
        self.assertTrue(soup.find('td', string='Subaru Outback'))
        self.assertTrue(soup.find('td', string='Honda Odyssey'))

    def test_leaders_encouraged_to_submit(self):
        trip = factories.TripFactory.create(info=None)
        trip.leaders.add(self.viewing_participant)
        soup = self._render(trip)
        danger = soup.find(class_='alert alert-danger')
        self.assertTrue(danger.find('a', href=f'/trips/{trip.pk}/itinerary/'))

    @freeze_time("Wed, 16 Oct 2019 20:30:00 EST")
    def test_hiding_sensitive_info(self):
        old_trip = factories.TripFactory.create(
            trip_date=date(2019, 10, 10), info=factories.TripInfoFactory.create()
        )
        factories.SignUpFactory.create(
            trip=old_trip,
            on_trip=True,
            participant__emergency_info__allergies="bee stings",
        )
        soup = self._render(old_trip)
        info = soup.find(class_='alert alert-info')
        self.assertIn(
            "To preserve participant privacy, sensitive medical information has been redacted",
            strip_whitespace(info.text),
        )
        self.assertFalse(soup.find(string="bee stings"))
        self.assertTrue(soup.find(string="redacted"))
