"""
Utilities for creating JSON response structures pertaining to membership.

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
from typing import Any, Dict, Literal, Optional, TypedDict

from ws import models
from ws.utils import geardb
from ws.utils.dates import local_date

JsonDict = Dict[str, Any]


# This is a simple string literal we show to humans to summarize membership status.
Status = Literal[
    "Missing",
    "Missing Waiver",
    "Waiver Expired",
    "Active",
    "Missing Membership",
    "Expired",
]


class _OnlyMembershipDict(TypedDict):
    expires: Optional[str]
    active: bool
    email: Optional[str]


class _OnlyWaiverDict(TypedDict):
    expires: Optional[str]
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
        'membership': {'expires': None, 'active': False, 'email': None},
        'waiver': {'expires': None, 'active': False},
        'status': 'Missing',
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
    if membership['expires'] is None and waiver['expires'] is None:
        return 'Missing'

    if not membership['active']:
        return "Missing Membership" if waiver['active'] else "Expired"

    if not waiver['expires']:
        return "Missing Waiver"
    if not waiver['active']:
        return "Waiver Expired"
    return "Active"


def _format_membership(
    email: Optional[str],
    membership_expires: Optional[date],
    waiver_expires: Optional[date],
) -> MembershipDict:
    person = _blank_membership()
    membership, waiver = person['membership'], person['waiver']
    membership['email'] = email

    for component, expires in [
        (membership, membership_expires),
        (waiver, waiver_expires),
    ]:
        component['expires'] = expires.isoformat() if expires else None
        component['active'] = bool(expires and expires >= local_date())

    person['status'] = _represent_status(membership, waiver)

    return person
