from datetime import date

from django.test import SimpleTestCase
from freezegun import freeze_time

from ws.tests import factories
from ws.utils import geardb, membership_api


class JsonifyTest(SimpleTestCase):
    @freeze_time("2022-07-01 12:00 EDT")
    def test_jsonify_membership_waiver(self):
        membership_waiver = geardb.MembershipWaiver(
            email="tim@mit.edu",
            membership_expires=date(2022, 11, 11),
            waiver_expires=date(2022, 11, 13),
        )
        self.assertEqual(
            membership_api.jsonify_membership_waiver(membership_waiver),
            {
                "membership": {
                    "expires": "2022-11-11",
                    "active": True,
                    "email": "tim@mit.edu",
                },
                "waiver": {"expires": "2022-11-13", "active": True},
                "status": "Active",
            },
        )


class FormatCachedMembershipTest(SimpleTestCase):
    """Test translation of our internal cache to a JSON structure."""

    def test_active_or_inactive_member(self):
        """Test the usual case - a participant with a waiver & membership on file."""
        par = factories.ParticipantFactory.build(
            membership__membership_expires=date(2022, 11, 11),
            membership__waiver_expires=date(2022, 11, 13),
        )

        with freeze_time("2022-07-01 12:00 EDT"):
            self.assertEqual(
                membership_api.format_cached_membership(par),
                {
                    "membership": {
                        "expires": "2022-11-11",
                        "active": True,
                        "email": par.email,
                    },
                    "waiver": {"expires": "2022-11-13", "active": True},
                    "status": "Active",
                },
            )
        with freeze_time("2022-12-25 12:00 EDT"):
            self.assertEqual(
                membership_api.format_cached_membership(par),
                {
                    "membership": {
                        "expires": "2022-11-11",
                        "active": False,
                        "email": par.email,
                    },
                    "waiver": {"expires": "2022-11-13", "active": False},
                    "status": "Expired",
                },
            )

    @freeze_time("2022-07-01 12:00 EDT")
    def test_missing_membership(self):
        par = factories.ParticipantFactory.build(
            membership__membership_expires=None,
            membership__waiver_expires=date(2022, 12, 23),
        )
        self.assertEqual(
            membership_api.format_cached_membership(par),
            {
                "membership": {"expires": None, "active": False, "email": par.email},
                "waiver": {"expires": "2022-12-23", "active": True},
                "status": "Missing Membership",
            },
        )

    @freeze_time("2022-07-01 12:00 EDT")
    def test_missing_waiver(self):
        par = factories.ParticipantFactory.build(
            membership__membership_expires=date(2022, 12, 24),
            membership__waiver_expires=None,
        )
        self.assertEqual(
            membership_api.format_cached_membership(par),
            {
                "membership": {
                    "expires": "2022-12-24",
                    "active": True,
                    "email": par.email,
                },
                "waiver": {"expires": None, "active": False},
                "status": "Missing Waiver",
            },
        )

    @freeze_time("2022-07-01 12:00 EDT")
    def test_just_waiver_expired(self):
        par = factories.ParticipantFactory.build(
            membership__membership_expires=date(2022, 12, 24),
            membership__waiver_expires=date(2022, 1, 1),
        )
        self.assertEqual(
            membership_api.format_cached_membership(par),
            {
                "membership": {
                    "expires": "2022-12-24",
                    "active": True,
                    "email": par.email,
                },
                "waiver": {"expires": "2022-01-01", "active": False},
                "status": "Waiver Expired",
            },
        )

    def test_cache_exists_but_is_missing(self):
        par = factories.ParticipantFactory.build(
            membership__membership_expires=None,
            membership__waiver_expires=None,
        )
        self.assertEqual(
            membership_api.format_cached_membership(par),
            {
                "membership": {"expires": None, "active": False, "email": par.email},
                "waiver": {"expires": None, "active": False},
                "status": "Missing",
            },
        )

    def test_no_membership(self):
        par = factories.ParticipantFactory.build(membership=None)
        self.assertEqual(
            membership_api.format_cached_membership(par),
            {
                "membership": {"expires": None, "active": False, "email": None},
                "waiver": {"expires": None, "active": False},
                "status": "Missing",
            },
        )
