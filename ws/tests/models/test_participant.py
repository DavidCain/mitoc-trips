import datetime
import unittest
from datetime import date
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
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

    def test_email_addr(self):
        ada = factories.ParticipantFactory.build(
            name="Ada Lovelace", email="ada@example.com"
        )
        self.assertEqual(ada.email_addr, '"Ada Lovelace" <ada@example.com>')


class ReasonsCannotAttendTest(TestCase):
    def test_is_wimp(self):
        # Note that the participant also has no membership!
        # We *only* highlight the WIMP issue, since nothing else really matters.
        participant = factories.ParticipantFactory.create(membership=None)
        trip = factories.TripFactory.create(wimp=participant)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            [enums.TripIneligibilityReason.IS_TRIP_WIMP],
        )

    @freeze_time("12 Jan 2020 12:00:00 EST")
    def test_missed_lectures(self):
        # Note that the participant has no membership!
        participant = factories.ParticipantFactory.create(membership=None)

        # The trip takes place during Winter School, but they've missed lectures.
        trip = factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, trip_date=date(2020, 1, 19)
        )
        with mock.patch.object(date_utils, 'ws_lectures_complete') as lectures_over:
            lectures_over.return_value = True  # (Otherwise, won't be "missed")
            self.assertTrue(participant.missed_lectures_for(trip))
            all_reasons = participant.reasons_cannot_attend(trip)

        self.assertCountEqual(
            all_reasons,
            # We *only* highlight the lectures issue.
            # We don't want to prompt the user to pay membership dues
            [enums.TripIneligibilityReason.MISSED_WS_LECTURES],
        )

    def test_missed_lectures_but_attended_before(self):
        participant = factories.ParticipantFactory.create()
        factories.LectureAttendanceFactory.create(participant=participant, year=2016)

        def missed_lectures_for_trip_in_year(year) -> bool:
            """ Return if missing lectures for a trip in this year prohibits attendance. """
            trip = factories.TripFactory.create(
                program=enums.Program.WINTER_SCHOOL.value, trip_date=date(year, 1, 19)
            )
            with mock.patch.object(date_utils, 'ws_lectures_complete') as lectures_over:
                lectures_over.return_value = True  # (Otherwise, won't be "missed")
                with freeze_time(f"12 Jan {year} 12:00:00 EST"):
                    # (exhaust the generator while time is mocked)
                    reasons = set(participant.reasons_cannot_attend(trip))

            # Ignore other reasons, we only care about missing WS lectures
            return enums.TripIneligibilityReason.MISSED_WS_LECTURES in reasons

        # For normal participants, we always require attendance in the year of the trip
        self.assertFalse(missed_lectures_for_trip_in_year(2016))  # Attended that year!
        self.assertTrue(missed_lectures_for_trip_in_year(2017))
        self.assertTrue(missed_lectures_for_trip_in_year(2020))
        self.assertTrue(missed_lectures_for_trip_in_year(2021))

        # For WS leaders, attendance in the most recent 4 years permits signup
        factories.LeaderRatingFactory.create(
            participant=participant, activity=models.BaseRating.WINTER_SCHOOL,
        )
        self.assertFalse(missed_lectures_for_trip_in_year(2016))  # Attended that year!
        # For 4 years after last attendance, we permit an active leader to sign up for WS trips
        self.assertFalse(missed_lectures_for_trip_in_year(2017))
        self.assertFalse(missed_lectures_for_trip_in_year(2020))

        # After 4 years, the leader must attend again
        self.assertTrue(missed_lectures_for_trip_in_year(2021))
        self.assertTrue(missed_lectures_for_trip_in_year(2022))

    @freeze_time("12 Jan 2020 12:00:00 EST")
    def test_missed_lectures_as_first_time_ws_leader(self):
        """ If a first-time WS leader missed lectures, they are not allowed to participate. """
        participant = factories.ParticipantFactory.create()
        self.assertFalse(participant.lectureattendance_set.exists())

        trip = factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, trip_date=date(2020, 1, 19)
        )
        factories.LeaderRatingFactory.create(
            participant=participant, activity=models.BaseRating.WINTER_SCHOOL,
        )
        with mock.patch.object(date_utils, 'ws_lectures_complete') as lectures_over:
            lectures_over.return_value = True  # (Otherwise, won't be "missed")
            reasons = participant.reasons_cannot_attend(trip)

        self.assertCountEqual(
            reasons, {enums.TripIneligibilityReason.MISSED_WS_LECTURES}
        )

    @freeze_time("25 Oct 2018 12:00:00 EST")
    def test_problem_with_profile_legacy(self):
        """ If the affiliation was given before we started collecting more detail, warn! """
        participant = factories.ParticipantFactory.create(
            membership=factories.MembershipFactory.create(
                membership_expires=date(2019, 10, 10), waiver_expires=date(2019, 10, 10)
            )
        )
        self.assertCountEqual(
            participant.problems_with_profile, [enums.ProfileProblem.LEGACY_AFFILIATION]
        )
        trip = factories.TripFactory.create(program=enums.Program.CLIMBING)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            [enums.TripIneligibilityReason.PROFILE_PROBLEM],
        )

    def test_problems_with_profile_multiple(self):
        """ If a participant has multiple profile problems, we give only one reason. """
        participant = factories.ParticipantFactory.create(
            name="Cher",
            affiliation="S",
            emergency_info__emergency_contact__cell_phone='',
        )
        self.assertCountEqual(
            participant.problems_with_profile,
            [
                enums.ProfileProblem.MISSING_FULL_NAME,
                enums.ProfileProblem.INVALID_EMERGENCY_CONTACT_PHONE,
                enums.ProfileProblem.LEGACY_AFFILIATION,
            ],
        )

        trip = factories.TripFactory.create(program=enums.Program.CLIMBING.value)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            # We *only* highlight the lectures issue.
            # We don't want to prompt the user to pay membership dues
            [enums.TripIneligibilityReason.PROFILE_PROBLEM],
        )

    def test_no_membership_or_waiver(self):
        participant = factories.ParticipantFactory.create(membership=None)

        trip = factories.TripFactory.create(program=enums.Program.CLIMBING.value)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            [
                enums.TripIneligibilityReason.MEMBERSHIP_MISSING,
                enums.TripIneligibilityReason.WAIVER_MISSING,
            ],
        )

    @freeze_time("11 Dec 2019 12:00:00 EST")
    def test_expired_membership_and_waiver(self):
        participant = factories.ParticipantFactory.create(
            membership=factories.MembershipFactory.create(
                membership_expires=date(2018, 11, 1), waiver_expires=date(2018, 11, 1)
            )
        )

        trip = factories.TripFactory.create(program=enums.Program.CLIMBING.value)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            [
                enums.TripIneligibilityReason.MEMBERSHIP_NEEDS_RENEWAL,
                enums.TripIneligibilityReason.WAIVER_NEEDS_RENEWAL,
            ],
        )

    @freeze_time("11 Dec 2019 12:00:00 EST")
    def test_waiver_needs_renewal(self):
        participant = factories.ParticipantFactory.create(
            membership=factories.MembershipFactory.create(
                membership_expires=date(2020, 11, 4), waiver_expires=date(2019, 11, 1)
            )
        )
        self.assertCountEqual(participant.problems_with_profile, [])

        trip = factories.TripFactory.create(program=enums.Program.CLIMBING.value)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            [enums.TripIneligibilityReason.WAIVER_NEEDS_RENEWAL],
        )

    @freeze_time("11 Dec 2019 12:00:00 EST")
    def test_membership_needs_renewal(self):
        participant = factories.ParticipantFactory.create(
            membership=factories.MembershipFactory.create(
                membership_expires=date(2019, 11, 4), waiver_expires=date(2020, 11, 11)
            )
        )

        trip = factories.TripFactory.create(program=enums.Program.CLIMBING.value)
        self.assertCountEqual(
            participant.reasons_cannot_attend(trip),
            [enums.TripIneligibilityReason.MEMBERSHIP_NEEDS_RENEWAL],
        )


class ProblemsWithProfileTest(TestCase):
    def test_our_factory_is_okay(self):
        """ The participant factory that we use is expected to have no problems. """
        participant = factories.ParticipantFactory.create()
        self.assertFalse(any(participant.problems_with_profile))

    def test_no_cell_phone_on_emergency_contact(self):
        participant = factories.ParticipantFactory.create()
        e_contact = factories.EmergencyContactFactory.create(cell_phone='')
        participant.emergency_info.emergency_contact = e_contact
        participant.save()

        self.assertCountEqual(
            participant.problems_with_profile,
            [enums.ProfileProblem.INVALID_EMERGENCY_CONTACT_PHONE],
        )

    def test_full_name_required(self):
        participant = factories.ParticipantFactory.create(name='Cher')
        self.assertCountEqual(
            participant.problems_with_profile, [enums.ProfileProblem.MISSING_FULL_NAME]
        )

    def test_verified_email_required(self):
        participant = factories.ParticipantFactory.create()

        # Directly assign the participant an invalid email
        # (this should never happen, since we enforce that addresses come from user.emailaddress_set)
        participant.email = 'not-verified@example.com'

        self.assertCountEqual(
            participant.problems_with_profile,
            [enums.ProfileProblem.PRIMARY_EMAIL_NOT_VALIDATED],
        )

    def test_old_student_affiliation_dated(self):
        student = factories.ParticipantFactory.create(
            affiliation='S',  # Ambiguous! Is it an MIT student? non-MIT? Undergrad/grad?
            last_updated=date_utils.local_now(),
        )

        self.assertCountEqual(
            student.problems_with_profile, [enums.ProfileProblem.LEGACY_AFFILIATION]
        )

    def test_not_updated_since_affiliation_overhaul(self):
        """ Any participant with affiliation predating our new categories should re-submit! """
        # This is right before the time when we released new categories!
        before_cutoff = date_utils.localize(datetime.datetime(2018, 10, 27, 3, 15))

        participant = factories.ParticipantFactory.create()
        # Override the default "now" timestamp, to make participant's last profile update look old
        participant.profile_last_updated = before_cutoff
        participant.save()

        self.assertCountEqual(
            participant.problems_with_profile,
            [enums.ProfileProblem.STALE_INFO, enums.ProfileProblem.LEGACY_AFFILIATION],
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
        self.assertCountEqual(participant.allowed_programs, [])

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

        self.assertCountEqual(
            participant.allowed_programs,
            [
                enums.Program.BIKING,
                enums.Program.CIRCUS,
                enums.Program.NONE,
                enums.Program.SERVICE,
            ],
        )


class MembershipActiveTest(unittest.TestCase):
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


class AffiliationTest(SimpleTestCase):
    def test_is_student(self):
        for affiliation in ["MU", "MG", "NU", "NG"]:
            par = factories.ParticipantFactory.build(affiliation=affiliation)
            self.assertTrue(par.is_student)
        for affiliation in ["NA", "MA", "ML"]:
            par = factories.ParticipantFactory.build(affiliation=affiliation)
            self.assertFalse(par.is_student)

    def test_annual_dues(self):
        def _dues_for(affiliation):
            par = factories.ParticipantFactory.build(affiliation=affiliation)
            return par.annual_dues

        # NOTE: These may change if the version of `mitoc_const` changes!
        for mit_student in ["MU", "MG"]:
            self.assertEqual(_dues_for(mit_student), 15)

        self.assertEqual(_dues_for("MA"), 30)
        for non_mit_student in ["NA", "NU", "NG"]:
            self.assertEqual(_dues_for(non_mit_student), 40)


class MissedLectureTests(TestCase):
    """ Test the logic that checks if a participant has missed lectures. """

    def test_legacy_years(self):
        """ Participants are not marked as missing lectures in first years. """
        # We lack records for these early years, so we just assume presence
        participant = factories.ParticipantFactory.create()
        # We can't say for sure that the participant attended for either year
        self.assertFalse(participant.attended_lectures(2014))
        self.assertFalse(participant.attended_lectures(2015))

        # But we also don't regard them as having "missed" since we don't have a record
        self.assertFalse(participant.missed_lectures(2014))
        self.assertFalse(participant.missed_lectures(2015))
        past_trip = factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, trip_date=date(2015, 1, 17)
        )
        self.assertFalse(participant.missed_lectures_for(past_trip))

    @freeze_time("Thursday, Jan 4 2018 15:00:00 EST")
    def test_lectures_incomplete(self):
        """ If this year's lectures haven't completed, nobody can be absent. """
        participant = factories.ParticipantFactory.create()

        # Participant hasn't attended.
        self.assertFalse(participant.attended_lectures(2018))

        # But, since lectures aren't complete, they didn't miss.
        with mock.patch.object(date_utils, 'ws_lectures_complete') as lectures_complete:
            lectures_complete.return_value = False
            self.assertFalse(participant.missed_lectures(2018))

        # Importantly, they aren't considered "missed" with regards to weekend trips
        sat_trip = factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, trip_date=date(2015, 1, 6)
        )
        self.assertFalse(participant.missed_lectures_for(sat_trip))

    @freeze_time("Thursday, Jan 19 2018 15:00:00 EST")
    def test_current_year(self):
        """ Check attendance in current year, after lectures complete.

        We're in a year where attendance is recorded, and we're asking about the current
        year. Did the participant attend?
        """
        par = factories.ParticipantFactory.create()
        factories.LectureAttendanceFactory.create(
            year=2017, participant=par, creator=par
        )
        self.assertTrue(par.attended_lectures(2017))

        self.assertFalse(par.attended_lectures(2018))
        with mock.patch.object(date_utils, 'ws_lectures_complete') as lectures_complete:
            # If lectures are not yet complete, we don't regard them as missing
            lectures_complete.return_value = False
            self.assertFalse(par.missed_lectures(2018))

            # If lectures are complete, they're counted as missing
            lectures_complete.return_value = True
            self.assertTrue(par.missed_lectures(2018))

        # When the participant attended, they did not miss lectures
        factories.LectureAttendanceFactory.create(
            year=2018, participant=par, creator=par
        )
        with mock.patch.object(date_utils, 'ws_lectures_complete') as lectures_complete:
            lectures_complete.return_value = True
            self.assertFalse(par.missed_lectures(2018))
