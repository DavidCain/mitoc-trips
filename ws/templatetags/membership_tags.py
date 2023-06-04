from collections.abc import Mapping
from types import MappingProxyType

from django import template

from ws import models
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
        "Missing Membership": "label-warning",
        "Expiring Soon": "label-info",
    }
)


@register.inclusion_tag('for_templatetags/membership_status.html')
def membership_status(
    participant: models.Participant,
    can_link_to_pay_dues: bool,
    can_link_to_sign_waiver: bool,
    personalize: bool,
):
    try:
        membership = participant.membership
    except AttributeError:
        membership = get_latest_membership(participant)

    can_renew_early = bool(membership and membership.in_early_renewal_period)

    membership_info = membership_api.format_cached_membership(participant)
    status = "Expiring Soon" if can_renew_early else membership_info['status']

    link_to_pay_dues = can_link_to_pay_dues and (
        can_renew_early or not (membership and membership.membership_active)
    )

    # Waivers can be signed free of cost any time.
    # But there's no sense in prompting people too early.
    #
    # We only need to provide a link if:
    # 1. waiver is expired
    # 2. we're prompting an early renewal of membership
    link_to_sign_waiver = can_link_to_sign_waiver and (
        can_renew_early or not (membership and membership.waiver_active)
    )

    # query_geardb_for_membership(user)
    return {
        'participant': participant,
        'membership': membership,
        'status': status,
        'in_early_renewal_period': can_renew_early,
        'label_class': STATUS_TO_BOOTSTRAP_LABEL[status],
        'link_to_pay_dues': link_to_pay_dues,
        'link_to_sign_waiver': link_to_sign_waiver,
        'personalize': personalize,
    }
