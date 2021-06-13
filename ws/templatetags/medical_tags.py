from datetime import timedelta

from django import template

import ws.utils.dates as date_utils
import ws.utils.perms as perm_utils
from ws import forms
from ws.utils.itinerary import get_cars

register = template.Library()


@register.inclusion_tag('for_templatetags/show_wimp.html')
def show_wimp(wimp):
    return {
        'participant': wimp,
    }


@register.inclusion_tag('for_templatetags/trip_itinerary.html')
def trip_itinerary(trip):
    """Return a stripped form for read-only display.

    Drivers will be displayed separately, and the 'accuracy' checkbox
    isn't needed for display.
    """
    if not trip.info:
        return {'info_form': None}
    info_form = forms.TripInfoForm(instance=trip.info)
    info_form.fields.pop('drivers')
    info_form.fields.pop('accurate')
    return {'info_form': info_form}


@register.inclusion_tag('for_templatetags/trip_info.html', takes_context=True)
def trip_info(context, trip, show_participants_if_no_itinerary=False):
    participant = context['viewing_participant']

    # After a sufficiently long waiting period, hide medical information
    # (We could need medical info a day or two after a trip was due back)
    # Some trips last for multiple days (trip date is Friday, return is Sunday)
    # Because we only record a single trip date, give a few extra days' buffer
    is_old_trip = date_utils.local_date() > (trip.trip_date + timedelta(days=5))

    return {
        'trip': trip,
        'participants': (
            trip.signed_up_participants.filter(signup__on_trip=True).select_related(
                'emergency_info__emergency_contact'
            )
        ),
        'trip_leaders': (
            trip.leaders.select_related('emergency_info__emergency_contact')
        ),
        'cars': get_cars(trip),
        'show_participants_if_no_itinerary': show_participants_if_no_itinerary,
        'hide_sensitive_info': is_old_trip,
        'is_trip_leader': perm_utils.leader_on_trip(participant, trip),
    }
