from bs4 import BeautifulSoup

from ws.tests import TestCase, factories


class AccountTests(TestCase):
    def _assert_no_scripts(self, response, user=None):
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertIsNone(soup.find('script'))
        self.assertIsNone(soup.find(class_='fa'))  # No use of FontAwesome

        if user and user.is_authenticated:
            title = 'For security, all scripts have been disabled on this page. Return to your profile?'
            self.assertTrue(soup.find('a', href='/', title=title))

        nav_menu = soup.find(id='main-menu')
        # The minimal menu has the two key links anyone needs!
        self.assertTrue(nav_menu.find('a', href='/help/', text='Help'))
        self.assertTrue(nav_menu.find('a', href='/contact/', text='Contact'))

        # There is nothing using Bootstrap's collapsible classes
        self.assertFalse(nav_menu.find(class_="collapse"))
        self.assertFalse(nav_menu.find(class_="collapsed"))

    def test_unauthenticated_user_routes(self):
        """ We load zero scripts on account management routes for anonymous_users. """
        self._assert_no_scripts(self.client.get('/accounts/login/'))
        self._assert_no_scripts(self.client.get('/accounts/signup/'))

    def test_noscript_on_password_change(self):
        """ For an authenticated user, we don't load JS for password change. """
        user = factories.UserFactory.create()
        self.client.force_login(user)

        self._assert_no_scripts(self.client.get('/accounts/password/change/'), user)

    def test_acceptable_routes_for_javascript(self):
        """ Pages in which secure credentials are not transmitted can have JS. """
        response = self.client.get('/accounts/password/reset/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('<script', response.content.decode())
