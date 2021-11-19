from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from django.test import Client
from freezegun import freeze_time

import ws.utils.dates as date_utils
import ws.utils.perms as perm_utils
from ws import enums, models
from ws.tests import TestCase, factories, strip_whitespace


class Helpers:
    client: Client

    def _get(self, url: str):
        response = self.client.get(url)
        assert response.status_code == 200, str(response.status_code)
        soup = BeautifulSoup(response.content, 'html.parser')
        return response, soup


class ClimbingLeaderApplicationTest(TestCase, Helpers):
    """Climbing leaders apply via a special Google Form."""

    BASE_FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSeWeIjtQ-p4mH_zGS-YvedvkbmVzBQOarIvzfzBzEgHMKuZzw'

    @staticmethod
    def _create_application_and_approve():
        application = factories.ClimbingLeaderApplicationFactory.create(
            # Note that the form logic usually handles this
            year=date_utils.local_date().year,
        )
        factories.LeaderRatingFactory.create(
            activity=enums.Activity.CLIMBING.value,
            participant=application.participant,
        )
        return application

    def setUp(self):
        self.participant = factories.ParticipantFactory.create(name='Tim Beaver')
        self.client.force_login(self.participant.user)

    def test_climbing_application_via_google_form(self):
        _response, soup = self._get('/climbing/leaders/apply/')

        # For clients on tablets or larger, we embed a form
        soup.find(
            'iframe',
            attrs={
                'class': 'hidden-sm',
                # Form is embedded, pre-filled with participant's name
                'src': f'{self.BASE_FORM_URL}/viewform?embedded=true&entry.1371106720=Tim+Beaver',
            },
        )

        # We link straight to the form, for those on mobile (or who prefer to not use embedded)
        soup.find(
            'a',
            attrs={
                'href': f'{self.BASE_FORM_URL}/viewform?entry.1371106720=Tim+Beaver',
            },
        )

        # Page also includes our general description on climbing ratings
        help_section_start = soup.find('h3')
        self.assertEqual(help_section_start.text, 'For all climbing leaders:')
        self.assertEqual(
            help_section_start.find_next('li').text,
            'You have strong group management skills.',
        )

    def test_submission_blocked(self):
        """Even though the ClimbingLeaderApplication model exists, you can't apply."""
        resp = self.client.post(
            '/climbing/leaders.apply',
            {'outdoor_sport_leading_grade': '5.11d'},
        )
        self.assertEqual(resp.status_code, 404)

    def test_old_applications_climbing(self):
        with freeze_time("2018-08-13 18:45 EDT"):
            self._create_application_and_approve()
        with freeze_time("2019-06-22 12:23 EDT"):
            self._create_application_and_approve()

        perm_utils.make_chair(self.participant.user, enums.Activity.CLIMBING)
        _response, soup = self._get('/climbing/applications/')
        self.assertEqual(
            soup.find('p').text,
            'Only archived climbing leader applications appear here.',
        )
        self.assertEqual(
            [h2.text for h2 in soup.find_all('h2')],
            [
                'Leader Applications',
                'Past Applications - 2019',
                'Past Applications - 2018',
            ],
        )

    def test_no_applications_climbing(self):
        perm_utils.make_chair(self.participant.user, enums.Activity.CLIMBING)
        _response, soup = self._get('/climbing/applications/')

        self.assertEqual(
            soup.find('p').text,
            'Only archived climbing leader applications appear here.',
        )

    def test_invalid_activity(self):
        response = self.client.get('/ice-fishing/applications/')
        self.assertEqual(response.status_code, 404)

    def test_not_a_chair(self):
        response = self.client.get('/climbing/applications/')
        self.assertEqual(response.status_code, 403)

    def test_not_a_chair_for_the_activity(self):
        perm_utils.make_chair(self.participant.user, enums.Activity.CLIMBING)
        response = self.client.get('/hiking/applications/')
        self.assertEqual(response.status_code, 403)


class BikingLeaderApplicationTest(TestCase):
    """We don't have a biking leader application."""

    def test_404(self):
        self.client.force_login(factories.ParticipantFactory.create().user)
        response = self.client.get('/biking/leaders/apply/')
        self.assertEqual(response.status_code, 404)


class HikingLeaderApplicationTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_preamble(self):
        _response, soup = self._get('/hiking/leaders/apply/')
        self.assertEqual(
            strip_whitespace(soup.find('h1').text), 'Hiking Leader Application'
        )
        self.assertEqual(
            soup.find('p').text,
            "Please complete and submit the form below if you're interested in becoming a MITOC Hiking Leader.",
        )

    def test_key_fields_hidden(self):
        _response, soup = self._get('/hiking/leaders/apply/')
        # The year is automatically added by the server.
        self.assertFalse(soup.find('input', attrs={'name': 'year'}))
        # The participant is given by the session, and added to the form by the server.
        self.assertFalse(soup.find('input', attrs={'name': 'participant'}))
        # Previous rating is provided by the system.
        self.assertFalse(soup.find('input', attrs={'name': 'previous_rating'}))

    def test_submission(self):
        response = self.client.post(
            '/hiking/leaders/apply/',
            {
                'desired_rating': 'Co-Leader',
                'mitoc_experience': 'No club experience - I just moved to Cambridge!',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/hiking/leaders/apply/")

    def test_existing_application_cannot_reapply(self):
        self.client.post(
            '/hiking/leaders/apply/',
            {
                'desired_rating': 'Leader',
                'mitoc_experience': 'Never been hiking before',
            },
        )
        response, soup = self._get('/hiking/leaders/apply/')
        self.assertFalse(response.context['can_apply'])
        self.assertEqual(
            soup.find('div', class_='alert-info').text.strip(),
            "You've submitted your leader application, and it's awaiting review.",
        )
        self.assertTrue(soup.find('p', text='Never been hiking before'))

    def test_can_reapply_if_old_application_ignored(self):
        with freeze_time("2020-10-01 12:00 EST"):
            self.client.post(
                '/hiking/leaders/apply/',
                {
                    'desired_rating': 'Co-Leader',
                    'mitoc_experience': 'No club experience - I just moved to Cambridge!',
                },
            )

        # At least 180 days have passed.
        with freeze_time("2021-08-01 12:00 EST"):
            # Maybe this leader wants to upgrade to be a full leader.
            response, soup = self._get('/hiking/leaders/apply/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_apply'])
        self.assertTrue(response.context['application'])

        self.assertEqual(
            soup.find('p').text,
            "Please complete and submit the form below if you're interested in becoming a MITOC Hiking Leader.",
        )
        self.assertEqual(soup.find_all('h3')[1].text.strip(), "Most Recent Application")

    def test_can_apply_as_a_current_leader(self):
        factories.LeaderRatingFactory.create(
            activity=enums.Activity.HIKING.value,
            participant=self.participant,
            rating="Co-Leader",
        )

        response, soup = self._get('/hiking/leaders/apply/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['can_apply'])

        # We should probably say "if you want to upgrade" but maybe another day.
        self.assertEqual(
            soup.find('p').text,
            "Please complete and submit the form below if you're interested in becoming a MITOC Hiking Leader.",
        )


@freeze_time("2020-10-20 14:56:00 EST")
class WinterSchoolLeaderApplicationTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_title(self):
        _response, soup = self._get('/winter_school/leaders/apply/')
        self.assertEqual(
            strip_whitespace(soup.find('h1').text),
            'Winter School 2021 Leader Application',
        )


class AllLeaderApplicationsRecommendationTest(TestCase, Helpers):
    """Tests for the 'needs recommendation' vs. 'needs rating' mechanism."""

    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_0_activity_chairs(self):
        self.participant.user.is_superuser = True
        self.participant.user.save()
        self.assertFalse(Group.objects.get(name='hiking_chair').user_set.exists())

        application = factories.HikingLeaderApplicationFactory.create()
        response, soup = self._get('/hiking/applications/')

        # There are no chairs. Thus, the application needs no recommendation, just a rating.
        self.assertEqual(response.context_data['needs_rec'], [])
        self.assertEqual(response.context_data['needs_rating'], [application])

        self.assertEqual(
            strip_whitespace(soup.find('div', attrs={'class': 'alert-info'}).text),
            "When there are multiple activity chairs, co-chairs can make recommendations to one another. "
            "However, this doesn't really make sense when there is not an acting chair.",
        )

    def test_1_activity_chair(self):
        Group.objects.get(name='hiking_chair').user_set.set([self.participant.user])

        application = factories.HikingLeaderApplicationFactory.create()
        response, soup = self._get('/hiking/applications/')

        self.assertEqual(response.context_data['needs_rec'], [])
        self.assertEqual(response.context_data['needs_rating'], [application])

        self.assertEqual(
            strip_whitespace(soup.find('div', attrs={'class': 'alert-info'}).text),
            "When there are multiple activity chairs, co-chairs can make recommendations to one another. "
            "However, this doesn't really make sense when there's a single chair.",
        )

    def test_2_activity_chairs(self):
        Group.objects.get(name='hiking_chair').user_set.set(
            [self.participant.user, factories.ParticipantFactory.create().user]
        )

        # Neither chair have recommended one application
        no_recs_application = factories.HikingLeaderApplicationFactory.create()

        response_1, soup_1 = self._get('/hiking/applications/')
        self.assertEqual(response_1.context_data['needs_rec'], [no_recs_application])
        self.assertEqual(response_1.context_data['needs_rating'], [])
        self.assertEqual(
            strip_whitespace(soup_1.find('div', attrs={'class', 'alert-info'}).text),
            'Recommend some leader ratings for other applications to populate this list.',
        )

        # Viewing chair gave a recommendation for one application
        one_rec_application = factories.HikingLeaderApplicationFactory.create()
        factories.LeaderRecommendationFactory.create(
            creator=self.participant,
            participant=one_rec_application.participant,
            activity=enums.Activity.HIKING.value,
        )

        response, soup = self._get('/hiking/applications/')
        self.assertEqual(response.context_data['needs_rec'], [no_recs_application])
        self.assertEqual(response.context_data['needs_rating'], [one_rec_application])
        self.assertIsNone(soup.find('div', attrs={'class', 'alert-info'}))


class AllLeaderApplicationsTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    @staticmethod
    def _create_application_and_approve():
        application = factories.HikingLeaderApplicationFactory.create(
            # Note that the form logic usually handles this
            year=date_utils.local_date().year,
        )
        factories.LeaderRatingFactory.create(
            activity=enums.Activity.HIKING.value, participant=application.participant
        )
        return application

    def test_no_applications(self):
        Group.objects.get(name='hiking_chair').user_set.add(self.participant.user)
        _response, soup = self._get('/hiking/applications/')
        self.assertEqual(
            soup.find('p').text, 'There are no leader applications pending your review.'
        )

    def test_only_approved_applications(self):
        Group.objects.get(name='hiking_chair').user_set.add(self.participant.user)
        with freeze_time("2018-08-13 18:45 EDT"):
            self._create_application_and_approve()

        _response, soup = self._get('/hiking/applications/')
        self.assertEqual(
            soup.find('p').text, 'There are no leader applications pending your review.'
        )
        self.assertEqual(
            [h2.text for h2 in soup.find_all('h2')],
            [
                'Leader Applications',
                'Past Applications - 2018',
            ],
        )

    def test_no_form_defined(self):
        Group.objects.get(name='boating_chair').user_set.add(self.participant.user)

        _response, soup = self._get('/boating/applications/')
        self.assertEqual(
            soup.find('p').text, 'There are no leader applications pending your review.'
        )
        self.assertIn(
            "You don't have any application form defined for Boating!",
            soup.find('div', attrs={'class': 'alert-warning'}).text,
        )


class LeaderApplicationsBaseTest(TestCase, Helpers):
    def _expect_form_contents(self, soup, rating: str, notes: str, submit: str):
        form = soup.find('form')
        rating_input = form.find('input', attrs={'name': 'rating'})
        notes_textarea = form.find('textarea', attrs={'name': 'notes'})
        submit_btn = form.find('button', attrs={'type': 'submit'})

        self.assertEqual(notes_textarea.text.strip(), notes)
        self.assertEqual(rating_input.attrs.get('value', ''), rating)
        # (AngularJS quirk: The submit button has two spans for conditional content rendering.
        # Just use the first one, which is set by the server until AngularJS overrides.
        self.assertEqual(submit_btn.find('span').text.strip(), submit)


class LeaderApplicationsTest(LeaderApplicationsBaseTest):
    """Tests an activity chair's interaction with applications, making ratings/recs."""

    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

        perm_utils.make_chair(self.participant.user, enums.Activity.HIKING)

    def test_unknown_activity(self):
        response = self.client.get('/curling/applications/1/')
        self.assertEqual(response.status_code, 404)

    def test_not_a_chair_for_that_activity(self):
        response = self.client.get('/climbing/applications/1/')
        self.assertEqual(response.status_code, 403)

    def test_invalid_post(self):
        application = factories.HikingLeaderApplicationFactory.create()
        response = self.client.post(
            f'/hiking/applications/{application.pk}/',
            {
                'notes': 'I forgot the rating field',
                'is_recommendation': False,
            },
        )
        self.assertEqual(
            response.context['form'].errors, {'rating': ['This field is required.']}
        )

    def test_one_chair_one_application(self):
        """Test an activity with only one chair, viewing the only application."""
        application = factories.HikingLeaderApplicationFactory.create()
        url = f'/hiking/applications/{application.pk}/'
        _response, soup = self._get(url)

        # There are no other applications needing attention
        prev_button, next_button = soup.find_all(
            'a', attrs={'role': 'button', 'class': 'prev-next-app'}
        )
        self.assertIn('disabled', prev_button.attrs)
        self.assertIn('disabled', next_button.attrs)

        # Because there's only one chair, we default to ratings, not recommendations
        self._expect_form_contents(soup, rating='', notes='', submit='Create rating')

        # Submitting the form on the page creates a rating!
        self.client.post(
            url,
            {
                'rating': 'Co-leader',
                'notes': 'Request an upgrade after leading 2 trips',
                'is_recommendation': False,
            },
        )

        rating = models.LeaderRating.objects.get(participant=application.participant)

        self.assertEqual(rating.creator, self.participant)
        self.assertEqual(rating.participant, application.participant)
        self.assertTrue(rating.active)
        self.assertEqual(rating.rating, 'Co-leader')
        self.assertEqual(rating.activity, enums.Activity.HIKING.value)

    def test_multiple_applications(self):
        """Applications can be navigated between with the previous & next buttons."""
        app1 = factories.HikingLeaderApplicationFactory.create()
        app2 = factories.HikingLeaderApplicationFactory.create()
        app3 = factories.HikingLeaderApplicationFactory.create()

        url = f'/hiking/applications/{app2.pk}/'
        _response, soup = self._get(url)

        # We can advance back to the first app, or forward to the second
        prev_button, next_button = soup.find_all(
            'a', attrs={'role': 'button', 'class': 'prev-next-app'}
        )
        self.assertEqual(prev_button.attrs['href'], f'/hiking/applications/{app1.pk}/')
        self.assertEqual(next_button.attrs['href'], f'/hiking/applications/{app3.pk}/')

        # Submitting a recommendation goes to the next application
        response = self.client.post(
            url,
            {'rating': 'Full', 'notes': '', 'is_recommendation': False},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/hiking/applications/{app3.pk}/')

    def test_recommendation_only(self):
        """When there are two or more chairs, we encourage recommendations first."""
        perm_utils.make_chair(factories.UserFactory.create(), enums.Activity.HIKING)

        application = factories.HikingLeaderApplicationFactory.create()
        url = f'/hiking/applications/{application.pk}/'
        _response, soup = self._get(url)

        # Because there are two chairs, we default to suggesting a recommendation
        self._expect_form_contents(
            soup, rating='', notes='', submit='Create recommendation'
        )

        # Submitting the form on the page creates a recommendation!
        self.client.post(
            url,
            {'rating': 'Co-leader', 'notes': '', 'is_recommendation': True},
        )

        self.assertFalse(
            models.LeaderRating.objects.filter(participant=application.participant)
        )

        self.assertTrue(
            models.LeaderRecommendation.objects.filter(
                participant=application.participant,
                creator=self.participant,
                rating='Co-leader',
                notes='',
            ).exists()
        )

    def test_already_has_rating(self):
        """When viewing an application with a rating, you can update it.."""
        application = factories.HikingLeaderApplicationFactory.create()
        url = f'/hiking/applications/{application.pk}/'

        # Use the flow itself to make a rating.
        self.client.post(
            url,
            {'rating': 'Co-leader', 'notes': '', 'is_recommendation': False},
        )

        _response, soup = self._get(url)
        self._expect_form_contents(
            soup, rating='Co-leader', notes='', submit='Update rating'
        )

        self.client.post(
            url,
            {'rating': 'Leader', 'notes': 'Upgrade!', 'is_recommendation': False},
        )

        # We updated the rating by creating a new one and deactivating the old one
        rating = models.LeaderRating.objects.get(
            participant=application.participant, active=True
        )
        self.assertEqual(rating.rating, 'Leader')
        self.assertEqual(rating.notes, 'Upgrade!')

    def test_all_chairs_gave_differing_recommendations(self):
        other_chair = factories.ParticipantFactory.create()
        perm_utils.make_chair(other_chair.user, enums.Activity.HIKING)

        application = factories.HikingLeaderApplicationFactory.create()

        for chair, rating in [(self.participant, 'full'), (other_chair, 'co-lead')]:
            factories.LeaderRecommendationFactory.create(
                creator=chair,
                participant=application.participant,
                activity=enums.Activity.HIKING.value,
                rating=rating,
                notes='Not sure about this one',
            )

        _response, soup = self._get(f'/hiking/applications/{application.pk}/')

        # We prompt them to make a rating, but we don't pre-fill
        self._expect_form_contents(soup, rating='', notes='', submit='Create rating')

    def test_all_chairs_unanimous(self):
        """When all chairs gave the same recommendation, we pre-fill."""
        other_chair_1 = factories.ParticipantFactory.create(name='Pooh Bear')
        other_chair_2 = factories.ParticipantFactory.create()
        perm_utils.make_chair(other_chair_1.user, enums.Activity.HIKING)
        perm_utils.make_chair(other_chair_2.user, enums.Activity.HIKING)

        application = factories.HikingLeaderApplicationFactory.create()

        for chair in (self.participant, other_chair_1, other_chair_2):
            factories.LeaderRecommendationFactory.create(
                creator=chair,
                participant=application.participant,
                activity=enums.Activity.HIKING.value,
                rating="Full rating",
                # Consensus doesn't care about this.
                notes=f'Confident - sincerely, {chair.name} (#{chair.pk})',
            )

        _response, soup = self._get(f'/hiking/applications/{application.pk}/')

        # We prompt them to make a rating, with rating pre-filled!
        self._expect_form_contents(
            soup, rating='Full rating', notes='', submit='Create rating'
        )

        # Note that should an admin create an extra rating, we no longer pre-fill
        # This shouldn't really happen (admins don't make recs), but it's handled.
        factories.LeaderRecommendationFactory.create(
            creator=factories.ParticipantFactory.create(
                user=factories.UserFactory.create(is_superuser=True)
            ),
            participant=application.participant,
            activity=enums.Activity.HIKING.value,
            rating="I don't think we should",
        )
        _response, soup2 = self._get(f'/hiking/applications/{application.pk}/')
        self._expect_form_contents(soup2, rating='', notes='', submit='Create rating')

    def test_waiting_on_other_chairs(self):
        """We still default to recommendations while waiting for other chairs."""
        other_chair_1 = factories.ParticipantFactory.create()
        other_chair_2 = factories.ParticipantFactory.create()
        perm_utils.make_chair(other_chair_1.user, enums.Activity.HIKING)
        perm_utils.make_chair(other_chair_2.user, enums.Activity.HIKING)

        application = factories.HikingLeaderApplicationFactory.create()

        for chair in (self.participant, other_chair_1):
            factories.LeaderRecommendationFactory.create(
                creator=chair,
                participant=application.participant,
                activity=enums.Activity.HIKING.value,
                rating="Full rating",
            )

        url = f'/hiking/applications/{application.pk}/'
        _response, soup = self._get(url)

        self._expect_form_contents(
            soup, rating='Full rating', notes='', submit='Update recommendation'
        )
        self.client.post(url, {'rating': 'co', 'notes': '', 'is_recommendation': True})
        rec = models.LeaderRecommendation.objects.get(
            participant=application.participant, creator=self.participant
        )
        self.assertEqual(rec.rating, 'co')
        self.assertFalse(
            models.LeaderRating.objects.filter(participant=application.participant)
        )


class WinterSchoolLeaderApplicationsTest(LeaderApplicationsBaseTest):
    """Test the WS-specific special behavior for chairs interacting with applications."""

    def setUp(self):
        five_wsc = [factories.ParticipantFactory.create() for i in range(5)]
        for par in five_wsc:
            perm_utils.make_chair(par.user, enums.Activity.WINTER_SCHOOL)
        (_ws_chair1, _ws_chair2, self.wsc1, self.wsc2, self.wsc3) = five_wsc
        self.client.force_login(self.wsc1.user)

    def test_consensus_among_wsc(self):
        """The WS chairs are not counted when trying to identify consensus."""
        application = factories.WinterSchoolLeaderApplicationFactory.create()
        for chair in (self.wsc1, self.wsc2, self.wsc3):
            factories.LeaderRecommendationFactory.create(
                creator=chair,
                participant=application.participant,
                activity=enums.Activity.WINTER_SCHOOL.value,
                rating="A coB",
            )
        url = f'/winter_school/applications/{application.pk}/'

        _response, soup = self._get(url)

        self._expect_form_contents(
            soup, rating='A coB', notes='', submit='Create rating'
        )

    def test_awaiting_one_wsc_member(self):
        """We need three WSC members to give a rating for consensus."""
        application = factories.WinterSchoolLeaderApplicationFactory.create()
        factories.LeaderRecommendationFactory.create(
            creator=self.wsc1,
            participant=application.participant,
            activity=enums.Activity.WINTER_SCHOOL.value,
            rating="coB",
            notes="No WFA",
        )
        factories.LeaderRecommendationFactory.create(
            creator=self.wsc2,
            participant=application.participant,
            activity=enums.Activity.WINTER_SCHOOL.value,
            rating="coC",
            notes="Notes from the other participant",
        )
        url = f'/winter_school/applications/{application.pk}/'

        _response, soup = self._get(url)

        self._expect_form_contents(
            soup, rating="coB", notes="No WFA", submit='Update recommendation'
        )
