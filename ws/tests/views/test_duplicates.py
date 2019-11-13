from bs4 import BeautifulSoup

from ws.tests import TestCase, factories


class PotentialDuplicatesViewewTest(TestCase):
    def setUp(self):
        super().setUp()
        user = factories.UserFactory.create(is_superuser=True)
        self.client.force_login(user)

    def _get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        return response, soup

    def _assert_redirect_back(self, resp):
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/participants/potential_duplicates/')

    def test_get_post_routes(self):
        self._assert_redirect_back(self.client.get('/participants/1234/merge/9932'))
        self._assert_redirect_back(self.client.get('/participants/1234/distinct/9932'))

    def test_no_potential_duplicates(self):
        _response, soup = self._get('/participants/potential_duplicates/')
        self.assertEqual(
            soup.find(class_='alert-info').get_text(' ', strip=True),
            'No potential duplicates found!',
        )

    def test_same_cell_phone(self):
        old = factories.ParticipantFactory.create(
            name="Older Par", cell_phone="+18005552222"
        )
        new = factories.ParticipantFactory.create(
            name="Newer Par", cell_phone="+18005552222"
        )
        _response, soup = self._get('/participants/potential_duplicates/')

        form = soup.find(
            'form', attrs={'action': f'/participants/{old.pk}/merge/{new.pk}'}
        )

        # We redirect back to the page after submission
        submit = self.client.post(form['action'])
        self._assert_redirect_back(submit)
        _, soup = self._get(submit.url)

        self.assertEqual(
            soup.find(class_='alert-success').get_text(' ', strip=True),
            f"Merged Older Par (#{old.pk}) into Newer Par (#{new.pk})",
        )

        # Neither participant appears anymore
        self.assertIsNone(soup.find(text='Older Par'))
        self.assertIsNone(soup.find(text='Newer Par'))

    def test_same_name_mark_distinct(self):
        old = factories.ParticipantFactory.create(
            name="John Smith", cell_phone="+18005552222"
        )
        new = factories.ParticipantFactory.create(
            name="John Smith", cell_phone="+16175551234"
        )
        factories.ParticipantFactory.create(name='John Smithee')
        _response, soup = self._get('/participants/potential_duplicates/')
        form = soup.find(
            'form', attrs={'action': f'/participants/{old.pk}/distinct/{new.pk}'}
        )

        # We redirect back to the page after submission
        submit = self.client.post(form['action'])
        self._assert_redirect_back(submit)
        _, soup = self._get(submit.url)

        self.assertEqual(
            soup.find(class_='alert-success').get_text(' ', strip=True),
            f"Marked John Smith (#{old.pk}) as distinct from John Smith (#{new.pk})",
        )
        # Neither John Smith appears anymore.
        self.assertIsNone(soup.find(text='John Smith'))

    def test_merge_non_existent(self):
        old = factories.ParticipantFactory.create(name="Older Par")
        new = factories.ParticipantFactory.create(name="Newer Par")

        # First merge does what we expect, and moves the old into the new.
        resp = self.client.post(f'/participants/{old.pk}/merge/{new.pk}')
        self._assert_redirect_back(resp)
        _, soup = self._get(resp.url)
        self.assertEqual(
            soup.find(class_='alert-success').get_text(' ', strip=True),
            f"Merged Older Par (#{old.pk}) into Newer Par (#{new.pk})",
        )

        # Doing the same thing again will fail, since the old participant is migrated
        resp = self.client.post(f'/participants/{old.pk}/merge/{new.pk}')
        self._assert_redirect_back(resp)
        _, soup = self._get(resp.url)
        self.assertEqual(
            soup.find(class_='alert-danger').get_text(' ', strip=True),
            f"One of #{old.pk},#{new.pk} is missing",
        )

        # Similarly, we can't mark distinct now that they're merged
        resp = self.client.post(f'/participants/{old.pk}/distinct/{new.pk}')
        self._assert_redirect_back(resp)
        _, soup = self._get(resp.url)
        self.assertEqual(
            soup.find(class_='alert-danger').get_text(' ', strip=True),
            f"One of #{old.pk},#{new.pk} is missing",
        )

    def test_merge_collision(self):
        old = factories.ParticipantFactory.create(name="Older Par")
        new = factories.ParticipantFactory.create(name="Newer Par")

        # Put both participants on the same trip. We cannot merge these!
        trip = factories.TripFactory.create()
        factories.SignUpFactory.create(participant=old, trip=trip)
        factories.SignUpFactory.create(participant=new, trip=trip)

        resp = self.client.post(f'/participants/{old.pk}/merge/{new.pk}')
        self._assert_redirect_back(resp)
        _, soup = self._get(resp.url)

        error_message = soup.find(class_='alert-danger').get_text(' ', strip=True)
        self.assertTrue(
            error_message.startswith(
                "Unable to merge participants because of overlapping data!"
            )
        )
        self.assertIn(
            "Full message: duplicate key value violates unique constraint",
            error_message,
        )
