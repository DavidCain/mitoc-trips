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
