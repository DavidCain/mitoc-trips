from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any

from django import template
from django.template.context import Context

from ws import models
from ws.utils import dates as date_utils
from ws.utils import membership_api
from ws.utils.membership import get_latest_membership

register = template.Library()

STATUS_TO_BOOTSTRAP_LABEL: Mapping[membership_api.Status, str] = MappingProxyType(
    {
        "Active": "label-success",
        "Expired": "label-danger",
        "Missing": "label-danger",
        "Waiver Expired": "label-warning",
        "Missing Waiver": "label-warning",
        "Missing Dues": "label-warning",
        "Expiring Soon": "label-info",
    }
)


@register.inclusion_tag("for_templatetags/membership_status.html", takes_context=True)
def membership_status(  # noqa: PLR0913
    context: Context,
    participant: models.Participant,
    can_link_to_pay_dues: bool,
    can_link_to_sign_waiver: bool,
    personalize: bool,
    just_signed: bool = False,
) -> dict[str, Any]:
    try:
        membership = participant.membership
    except AttributeError:
        membership = get_latest_membership(participant)

    can_renew_early = bool(membership and membership.in_early_renewal_period)

    today = date_utils.local_date()
    waiver_valid_until = (
        today + timedelta(days=365)
        if just_signed
        else (membership.waiver_expires if membership else None)
    )

    if can_renew_early:
        status: membership_api.Status = "Expiring Soon"
    else:
        status = (
            membership_api.format_membership(
                participant.email,
                membership_expires=(
                    membership.membership_expires if membership else None
                ),
                waiver_expires=waiver_valid_until,
            )
            if just_signed
            else membership_api.format_cached_membership(participant)
        )["status"]

    link_to_pay_dues = can_link_to_pay_dues and (
        can_renew_early or not (membership and membership.dues_active)
    )

    # Waivers can be signed free of cost any time.
    # But there's no sense in prompting people too early.
    #
    # We only need to provide a link if:
    # 1. waiver is expired
    # 2. we're prompting an early renewal of membership
    link_to_sign_waiver = (
        can_link_to_sign_waiver
        and not just_signed
        and (can_renew_early or not (membership and membership.waiver_active))
    )

    return {
        "participant": participant,
        # For recent cache refreshes, show it accurately to the second!
        "datetime_format": (
            "M j, g:i:s a"  # "Nov 6, 8:45:59 pm" (adds seconds, drops the year)
            if membership
            and (datetime.now(UTC) - membership.last_cached) < timedelta(minutes=5)
            else "DATETIME_FORMAT"
        ),
        "membership": membership,
        "status": status,
        "in_early_renewal_period": can_renew_early,
        "label_class": STATUS_TO_BOOTSTRAP_LABEL[status],
        "link_to_pay_dues": link_to_pay_dues,
        "link_to_sign_waiver": link_to_sign_waiver,
        "next_url": context["request"].path,
        "personalize": personalize,
        "today": today,
        "waiver_valid_until": waiver_valid_until,
    }
