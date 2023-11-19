from collections import OrderedDict
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from freezegun import freeze_time

from ws.privacy import DataDump
from ws.tests import factories


class DataDumpTest(TestCase):
    def test_minimal_participant(self):
        with freeze_time("Fri, 11 Nov 2020 18:35:40 EST"):
            membership = factories.MembershipFactory.create(
                membership_expires=date(2020, 10, 30), waiver_expires=date(2020, 10, 29)
            )
        participant = factories.ParticipantFactory.create(membership=membership)
        data = DataDump(participant.pk)

        self.assertEqual(
            data.all_data,
            OrderedDict(
                [
                    (
                        "user",
                        {
                            "last_login": None,
                            "date_joined": mock.ANY,
                            "name": "Test Participant",
                            "profile_last_updated": mock.ANY,
                            "cell_phone": "",
                            "affiliation": "Non-affiliate",
                            "emails": [
                                {
                                    "email": participant.email,
                                    "verified": True,
                                    "primary": True,
                                }
                            ],
                        },
                    ),
                    (
                        "membership",
                        {
                            "membership_expires": date(2020, 10, 30),
                            "waiver_expires": date(2020, 10, 29),
                        },
                    ),
                    ("discounts", []),
                    ("car", None),
                    (
                        "medical",
                        {
                            "emergency_contact": {
                                "name": "My Mother",
                                "cell_phone": "+17815550342",
                                "relationship": "Mother",
                                "email": "mum@example.com",
                            },
                            "allergies": "None",
                            "medications": "None",
                            "medical_history": "None",
                        },
                    ),
                    ("lottery_info", None),
                    ("leader_ratings", {}),
                    ("leader_applications", {}),
                    ("winter_school_lecture_attendance", []),
                    ("trips", {"wimped": [], "led": [], "created": []}),
                    ("signups", []),
                    ("feedback", {"received": [], "given": []}),
                ]
            ),
        )

    def test_success(self):
        """Create a bunch of data about the participant, ensure that dumping it works."""
        participant = factories.ParticipantFactory.create()
        participant.discounts.add(factories.DiscountFactory.create())
        participant.car = factories.CarFactory.create()
        participant.save()
        factories.LeaderRatingFactory.create(participant=participant)
        factories.LeaderRatingFactory.create(creator=participant)
        factories.LotteryInfoFactory.create(participant=participant)

        factories.TripFactory.create(creator=participant, name="First trip")
        factories.TripFactory.create(creator=participant, name="Second trip")
        factories.FeedbackFactory.create(leader=participant)
        factories.FeedbackFactory.create(participant=participant)

        factories.SignUpFactory.create(on_trip=True, participant=participant)
        factories.SignUpFactory.create(on_trip=False, participant=participant)
        factories.SignUpFactory.create(on_trip=False, participant=participant)

        with freeze_time("Thu, 5 Jan 2017 18:35:40 EST"):
            factories.LectureAttendanceFactory.create(
                year=2017, participant=participant
            )
        with freeze_time("Thu, 10 Jan 2019 18:45:20 EST"):
            factories.LectureAttendanceFactory.create(
                year=2019, participant=participant
            )

        data = DataDump(participant.pk)
        results = data.all_data
        self.assertTrue(isinstance(results, OrderedDict))
        self.assertEqual(
            results["winter_school_lecture_attendance"],
            [
                {
                    "year": 2017,
                    "time_created": datetime(
                        2017, 1, 5, 18, 35, 40, tzinfo=ZoneInfo("America/New_York")
                    ),
                },
                {
                    "year": 2019,
                    "time_created": datetime(
                        2019, 1, 10, 18, 45, 20, tzinfo=ZoneInfo("America/New_York")
                    ),
                },
            ],
        )
        # (Won't inspect the results of every value, since factory defaults may change)
        # Just ensure that they're actually filled.
        self.assertTrue(results["feedback"]["received"])
        self.assertTrue(results["feedback"]["given"])
        self.assertTrue(results["lottery_info"])
        self.assertTrue(results["leader_ratings"])
        self.assertTrue(results["signups"])

    def test_participant_without_membership(self):
        participant = factories.ParticipantFactory.create(membership=None)
        data = DataDump(participant.pk)

        self.assertIsNone(data.all_data["membership"])

    def test_leader_school_applications(self):
        par = factories.ParticipantFactory.create()
        with freeze_time("01 Jul 2020 18:35:40 EST"):
            factories.WinterSchoolLeaderApplicationFactory.create(participant=par)
            factories.ClimbingLeaderApplicationFactory.create(participant=par)

        data = DataDump(par.pk)

        all_apps = data.all_data["leader_applications"]
        self.assertCountEqual(all_apps, ["Winter School", "Climbing"])
        self.assertEqual(
            all_apps["Winter School"],
            [
                {
                    "previous_rating": "",
                    "archived": False,
                    "year": 2021,
                    "desired_rating": "B coC",
                    "taking_wfa": "No",
                    "training": "EMT Basic",
                    "technical_skills": "I know how to self arrest",
                    "winter_experience": "Several years hiking in the Whites",
                    "ice_experience": "",
                    "ski_experience": "",
                    "other_experience": "Leader in my college outing club",
                    "notes_or_comments": "",
                    "mentorship_goals": "",
                    "mentor_activities": [],
                    "mentee_activities": [],
                }
            ],
        )
        self.assertEqual(
            all_apps["Climbing"],
            [
                {
                    "previous_rating": "",
                    "archived": False,
                    "year": 2021,
                    "desired_rating": "",
                    "years_climbing": 9,
                    "years_climbing_outside": 7,
                    "outdoor_bouldering_grade": "V3",
                    "outdoor_sport_leading_grade": "5.11",
                    "outdoor_trad_leading_grade": "Trad is too rad for me",
                    "familiarity_spotting": "none",
                    "familiarity_bolt_anchors": "very comfortable",
                    "familiarity_gear_anchors": "none",
                    "familiarity_sr": "some",
                    "spotting_description": "",
                    "tr_anchor_description": "",
                    "rappel_description": "",
                    "gear_anchor_description": "",
                    "formal_training": "Wilderness First Responder",
                    "teaching_experience": "Leader in my college outing club",
                    "notable_climbs": "The Nose of El Capitan",
                    "favorite_route": "Jaws II",
                    "extra_info": "An extinct giant sloth is largely responsible for the existence of the avocado.",
                }
            ],
        )
