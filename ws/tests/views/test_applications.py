from bs4 import BeautifulSoup

from ws.tests import TestCase, factories


class Helpers:
    def _get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        return response, soup


class ClimbingLeaderApplicationTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_preamble(self):
        _response, soup = self._get('/climbing/leaders/apply/')
        expected_preamble = (
            'Please fill out the form below to apply to become a climbing leader. '
            'In addition to this form, we require that applicants have '
            'two recommendations from current MITOC climbing leaders.'
        )
        self.assertEqual(soup.find('h1').text, 'Climbing Leader Application')
        self.assertEqual(soup.find('p').text, expected_preamble)

    def test_key_fields_hidden(self):
        """ With no default filter, we only show upcoming trips. """
        _response, soup = self._get('/climbing/leaders/apply/')
        # "Archived" is a value that's set by leaders on existing applications
        self.assertFalse(soup.find('input', attrs={'name': 'archived'}))
        # The year is automatically added by the server.
        self.assertFalse(soup.find('input', attrs={'name': 'year'}))
        # The participant is given by the session, and added to the form by the server.
        self.assertFalse(soup.find('input', attrs={'name': 'participant'}))
        # Previous rating is provided by the system.
        self.assertFalse(soup.find('input', attrs={'name': 'previous_rating'}))
