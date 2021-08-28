from ws.tests import TestCase, factories


class PrivacyTest(TestCase):
    def test_privacy_download(self):
        par = factories.ParticipantFactory.create(email='foo@example.com')
        self.client.force_login(par.user)
        resp = self.client.get('/privacy/download.json')
        self.assertTrue(isinstance(resp.json(), dict))

    def test_must_be_authed(self):
        resp = self.client.get('/privacy/download.json')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/accounts/login'))


class PrivacySettingsTest(TestCase):
    def test_must_be_authed(self):
        resp = self.client.get('/privacy/settings/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/accounts/login'))

    def test_must_have_participant(self):
        self.client.force_login(factories.UserFactory.create())
        resp = self.client.get('/privacy/settings/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/profile/edit/?next=/privacy/settings/')

    def test_gravatar_opt_out(self):
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        self.client.post('/privacy/settings/', {'gravatar_opt_out': True})
        par.refresh_from_db()
        self.assertTrue(par.gravatar_opt_out)

        self.client.post('/privacy/settings/', {'gravatar_opt_out': False})
        par.refresh_from_db()
        self.assertFalse(par.gravatar_opt_out)
