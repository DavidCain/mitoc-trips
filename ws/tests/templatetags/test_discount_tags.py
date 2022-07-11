from bs4 import BeautifulSoup
from django.template import Context, Template

from ws.tests import TestCase, factories


class DiscountTagsTest(TestCase):
    def test_no_discounts(self):
        html_template = Template(
            '{% load discount_tags %}{% active_discounts participant%}'
        )
        context = Context({'participant': factories.ParticipantFactory.create()})
        self.assertFalse(html_template.render(context).strip())

    def test_discounts(self):
        participant = factories.ParticipantFactory.create()
        gym = factories.DiscountFactory.create(name="Local Gym", url='example.com/gym')
        retailer = factories.DiscountFactory.create(
            name="Large Retailer", url='example.com/retail'
        )
        factories.DiscountFactory.create(name="Other Outing Club")

        participant.discounts.add(gym)
        participant.discounts.add(retailer)

        html_template = Template(
            '{% load discount_tags %}{% active_discounts participant%}'
        )
        context = Context({'participant': participant})
        raw_html = html_template.render(context)
        soup = BeautifulSoup(raw_html, 'html.parser')

        self.assertEqual(
            soup.find('p').get_text(' ', strip=True),
            'You are sharing your name, email address, and membership status with the following companies:',
        )
        self.assertEqual(
            [str(li) for li in soup.find('ul').find_all('li')],
            [
                '<li><a href="example.com/gym">Local Gym</a></li>',
                '<li><a href="example.com/retail">Large Retailer</a></li>',
            ],
        )

        self.assertTrue(
            soup.find(
                'a', string='discount preferences', href="/preferences/discounts/"
            )
        )
