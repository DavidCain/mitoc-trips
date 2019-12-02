import datetime
import unittest
from datetime import date

from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time

import ws.utils.dates as date_utils
from ws import enums, models
from ws.tests import TestCase, factories


class ParticipantTest(TestCase):
    def test_from_anonymous_user(self):
        self.assertIsNone(models.Participant.from_user(AnonymousUser()))

    def test_from_user(self):
        user = factories.UserFactory.create()
        self.assertIsNone(models.Participant.from_user(user))

    def test_from_user_with_participant(self):
        participant = factories.ParticipantFactory.create()
        self.assertEqual(models.Participant.from_user(participant.user), participant)
        self.assertEqual(
            models.Participant.from_user(participant.user, join_membership=True),
            participant,
        )


class ProblemsWithProfile(TestCase):
    # NOTE: These require TestCase since we do actual db lookups based on the record
    def test_our_factory_is_okay(self):
        """ The participant factory that we use is expected to have no problems. """
        participant = factories.ParticipantFactory.create()
        self.assertFalse(participant.problems_with_profile)

    def test_no_cell_phone_on_emergency_contact(self):
        participant = factories.ParticipantFactory.create()
        e_contact = factories.EmergencyContactFactory.create(cell_phone='')
        participant.emergency_info.emergency_contact = e_contact
        participant.save()

        self.assertEqual(
            participant.problems_with_profile,
            ["Please supply a valid number for your emergency contact."],
        )

    def test_full_name_required(self):
        participant = factories.ParticipantFactory.create(name='Cher')
        self.assertEqual(
            participant.problems_with_profile, ["Please supply your full legal name."]
        )

    def test_verified_email_required(self):
        participant = factories.ParticipantFactory.create()

        # Directly assign the participant an invalid email
        # (this should never happen, since we enforce that addresses come from user.emailaddress_set)
        participant.email = 'not-verified@example.com'

        self.assertEqual(
            participant.problems_with_profile,
            [
                'Please <a href="/accounts/email/">verify that you own not-verified@example.com</a>, '
                'or set your email address to one of your verified addresses.'
            ],
        )

    def test_xss_on_email_prevented(self):
        """ Returned strings can be trusted as HTML. """
        participant = factories.ParticipantFactory.create(
            email="</a><script>alert('hax')</script>@hacks.tld"
        )

        participant.user.emailaddress_set.update(verified=False)
        self.assertEqual(
            participant.user.emailaddress_set.get().email,  # (our factory assigns only one email)
            "</a><script>alert('hax')</script>@hacks.tld",
        )

        self.assertEqual(
            participant.problems_with_profile,
            [
                'Please <a href="/accounts/email/">verify that you own '
                # Note the HTML escaping!
                '&lt;/a&gt;&lt;script&gt;alert(&#39;hax&#39;)&lt;/script&gt;@hacks.tld</a>, '
                'or set your email address to one of your verified addresses.'
            ],
        )

    def test_old_student_affiliation_dated(self):
        student = factories.ParticipantFactory.create(affiliation='S')  # MIT or not?

        self.assertEqual(
            student.problems_with_profile, ["Please update your MIT affiliation."]
        )

    def test_not_updated_since_affiliation_overhaul(self):
        """ Any participant with affiliation predating our new categories should re-submit! """
        # This is right before the time when we released new categories!
        before_cutoff = date_utils.localize(datetime.datetime(2018, 10, 27, 3, 15))

        # Override the default "now" timestamp, to make participant's last profile update look old
        participant = factories.ParticipantFactory.create()
        participant.profile_last_updated = before_cutoff
        participant.save()

        self.assertEqual(
            participant.problems_with_profile, ["Please update your MIT affiliation."]
        )


class LeaderTest(TestCase):
    def test_name_with_rating_no_rating(self):
        """ Participants who aren't actively leaders just return their name. """
        trip = factories.TripFactory.create()
        participant = factories.ParticipantFactory.create(name='Tommy Caldwell')
        self.assertEqual('Tommy Caldwell', participant.name_with_rating(trip))

    def test_open_trip(self):
        """ When ratings aren't required, only the name is returned. """
        trip = factories.TripFactory.create(program=enums.Program.CIRCUS.value)
        participant = factories.ParticipantFactory.create(name='Tommy Caldwell')

        participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=participant,
                activity=models.BaseRating.WINTER_SCHOOL,
                rating='Full leader',
            )
        )
        self.assertEqual('Tommy Caldwell', participant.name_with_rating(trip))

    def test_past_rating(self):
        """ We will display a past rating that was applicable at the time! """
        alex = factories.ParticipantFactory.create(name='Alex Honnold')

        # Make an older rating to show this isn't used
        with freeze_time("2018-11-10 12:25:00 EST"):
            rating = factories.LeaderRatingFactory.create(
                participant=alex,
                activity=models.BaseRating.WINTER_SCHOOL,
                rating='co-leader',
                active=False,  # (presume was active at the time)
            )
            alex.leaderrating_set.add(rating)
        with freeze_time("2019-02-15 12:25:00 EST"):
            rating = factories.LeaderRatingFactory.create(
                participant=alex,
                activity=models.BaseRating.WINTER_SCHOOL,
                rating='Full leader',
                active=False,  # (presume was active at the time)
            )
            alex.leaderrating_set.add(rating)
        trip = factories.TripFactory.create(
            trip_date=date(2019, 2, 23), activity=models.BaseRating.WINTER_SCHOOL
        )

        # At present, Alex is not even a leader
        self.assertFalse(alex.is_leader)
        # However, when that past trip happened, he was a leader.
        self.assertEqual('Alex Honnold (Full leader)', alex.name_with_rating(trip))

    @freeze_time("2018-11-10 12:25:00 EST")
    def test_future_trip(self):
        john = factories.ParticipantFactory.create(name='John Long')

        john.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=john,
                activity=models.BaseRating.WINTER_SCHOOL,
                rating='Full leader',
            )
        )
        trip = factories.TripFactory.create(
            trip_date=date(2019, 10, 23), activity=models.BaseRating.WINTER_SCHOOL
        )
        self.assertEqual('John Long (Full leader)', john.name_with_rating(trip))

    def test_participants_cannot_lead(self):
        participant = factories.ParticipantFactory()
        self.assertFalse(participant.can_lead(enums.Program.WINTER_SCHOOL))
        # Even open programs aren't able to be led by any participant
        self.assertFalse(participant.can_lead(enums.Program.CIRCUS))

    def test_can_lead_own_activity_and_open(self):
        participant = factories.ParticipantFactory()
        participant.leaderrating_set.add(
            factories.LeaderRatingFactory.create(
                participant=participant, activity=enums.Activity.BIKING.value
            )
        )
        # Can only lead programs for own activity
        self.assertTrue(participant.can_lead(enums.Program.BIKING))
        self.assertFalse(participant.can_lead(enums.Program.CLIMBING))

        # Can lead all open programs
        self.assertTrue(participant.can_lead(enums.Program.CIRCUS))
        self.assertTrue(participant.can_lead(enums.Program.NONE))
        self.assertTrue(participant.can_lead(enums.Program.SERVICE))


class MembershipTest(unittest.TestCase):
    def test_no_cached_membership(self):
        """ Convenience methods on the participant require membership/waiver!"""
        par = factories.ParticipantFactory.build(membership=None)

        trip = factories.TripFactory.build(membership_required=True)

        # Both a waiver & a membership are required
        self.assertFalse(par.membership_active)
        self.assertTrue(par.should_renew_for(trip))
        self.assertTrue(par.should_sign_waiver_for(trip))

    def test_no_membership(self):
        membership = factories.MembershipFactory.build(
            membership_expires=None, waiver_expires=None
        )

        trip = factories.TripFactory.build(membership_required=True)

        # Both a waiver & a membership are required
        self.assertFalse(membership.membership_active)
        self.assertTrue(membership.should_renew_for(trip))
        self.assertTrue(membership.should_sign_waiver_for(trip))

    def test_no_cached_membership_but_not_required(self):
        membership = factories.MembershipFactory.build(
            membership_expires=None, waiver_expires=None
        )

        trip = factories.TripFactory.build(membership_required=False)

        self.assertFalse(membership.membership_active)

        # Membership isn't required, but a waiver still is.
        self.assertFalse(membership.should_renew_for(trip))
        self.assertTrue(membership.should_sign_waiver_for(trip))

    @freeze_time("11 Dec 2015 12:00:00 EST")
    def test_active_membership(self):
        membership = factories.MembershipFactory.build(
            membership_expires=date(2016, 11, 4), waiver_expires=None
        )
        self.assertTrue(membership.membership_active)

        trip = factories.TripFactory.create(trip_date=date(2015, 11, 17))

        self.assertFalse(membership.should_renew_for(trip))
        self.assertTrue(membership.should_sign_waiver_for(trip))

    @freeze_time("11 Dec 2025 12:00:00 EST")
    def test_stale_membership(self):
        membership = factories.MembershipFactory.build(
            # Both are in the past, so currently expired!
            membership_expires=date(2023, 11, 15),
            waiver_expires=date(2023, 11, 15),
        )

        trip = factories.TripFactory.create(trip_date=date(2025, 12, 12))
        self.assertFalse(membership.membership_active)
        self.assertTrue(membership.should_renew_for(trip))
        self.assertTrue(membership.should_sign_waiver_for(trip))

    @freeze_time("11 Dec 2025 12:00:00 EST")
    def test_very_distant_trip(self):
        membership = factories.MembershipFactory.build(
            # Renewed just the day before!
            membership_expires=date(2026, 12, 10),
            waiver_expires=date(2026, 12, 10),
        )

        # More than a year out!
        trip = factories.TripFactory.create(trip_date=date(2026, 12, 13))

        self.assertTrue(membership.membership_active)

        # Much to early to renew a membership (364 days into current membership!)
        # Signing a waiver won't do any good yet.
        self.assertFalse(membership.should_renew_for(trip))
        self.assertFalse(membership.should_sign_waiver_for(trip))

    def test_str(self):
        par = factories.ParticipantFactory.build(
            name="Frida Kahlo",
            membership=factories.MembershipFactory.build(
                membership_expires=date(2026, 11, 10), waiver_expires=date(2026, 12, 12)
            ),
        )
        self.assertEqual(
            str(par.membership),
            'Frida Kahlo, membership: 2026-11-10, waiver: 2026-12-12',
        )
