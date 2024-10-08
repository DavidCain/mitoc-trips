"""Utilities for creating JSON response structures pertaining to membership.

Basic structure of the shared response type:

     {
        'membership': {
            'expires': 'YYYY-MM-DD',  # Or None
            'active': True,
            'email': 'tim@mit.edu',  # Or None
        },
        'waiver': {
            'expires': 'YYYY-MM-DD',  # Or None
            'active': True,
        },
        'status': 'Missing',
    }
"""

from datetime import date
from typing import Any, Literal, TypedDict

from ws import models
from ws.utils import geardb
from ws.utils.dates import local_date

JsonDict = dict[str, Any]


# This is a simple string literal we show to humans to summarize MITOC account status.
Status = Literal[
    "Missing",
    "Missing Waiver",
    "Waiver Expired",
    "Active",
    "Expiring Soon",  # (optional subtype of `Active`)
    "Missing Dues",
    "Expired",
]


class _OnlyMembershipDict(TypedDict):
    expires: str | None
    active: bool
    email: str | None


class _OnlyWaiverDict(TypedDict):
    expires: str | None
    active: bool


class MembershipDict(TypedDict):
    membership: _OnlyMembershipDict
    waiver: _OnlyWaiverDict
    status: Status


def jsonify_membership_waiver(mem: geardb.MembershipWaiver) -> MembershipDict:
    return _format_membership(
        mem.email,
        mem.membership_expires,
        mem.waiver_expires,
    )


def _blank_membership() -> MembershipDict:
    return {
        "membership": {"expires": None, "active": False, "email": None},
        "waiver": {"expires": None, "active": False},
        "status": "Missing",
    }


def format_cached_membership(participant: models.Participant) -> MembershipDict:
    """Format a ws.models.Membership object as a server response."""
    mem = participant.membership
    if mem is None:
        return _blank_membership()
    return _format_membership(
        participant.email,
        mem.membership_expires,
        mem.waiver_expires,
    )


def _represent_status(
    membership: _OnlyMembershipDict,
    waiver: _OnlyWaiverDict,
) -> Status:
    """Generate a human-readable status (for use in the UI)."""
    if membership["expires"] is None and waiver["expires"] is None:
        return "Missing"

    if not membership["active"]:
        return "Missing Dues" if waiver["active"] else "Expired"

    if not waiver["expires"]:
        return "Missing Waiver"
    if not waiver["active"]:
        return "Waiver Expired"
    return "Active"


def _format_membership(
    email: str | None,
    membership_expires: date | None,
    waiver_expires: date | None,
) -> MembershipDict:
    person = _blank_membership()
    membership, waiver = person["membership"], person["waiver"]
    membership["email"] = email

    for component, expires in [
        (membership, membership_expires),
        (waiver, waiver_expires),
    ]:
        component["expires"] = expires.isoformat() if expires else None
        component["active"] = bool(expires and expires >= local_date())

    person["status"] = _represent_status(membership, waiver)

    return person
