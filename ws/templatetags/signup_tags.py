from itertools import chain

from django import template
from django.forms import HiddenInput

from ws.forms import SignUpForm
from ws.utils.dates import local_date

register = template.Library()


def leader_signup_allowed(trip, participant):
    """ Determine whether or not to display the leader signup form.

    Note: This is not validation - the user's ultimate ability to sign
    up by a leader is determined by the logic in the models and views.
    """
    if not (participant and participant.is_leader):
        return False
    trip_upcoming = local_date() <= trip.trip_date

    return (trip_upcoming and trip.allow_leader_signups and
            participant.can_lead(trip.activity))


@register.inclusion_tag('for_templatetags/signup_for_trip.html', takes_context=True)
def signup_for_trip(context, trip, participant, existing_signup=None):
    """ Display the appropriate signup controls for a given trip.

    Signups are forbidden in a number of cases (trip already happened, signups
    aren't open yet, et cetera). There are a number of special cases where
    signups might be allowed anyway (e.g. the participant is a MITOC leader).

    This tag displays the appropriate controls to the viewing participant.
    """
    context = {
        'user': context['user'],
        'trip': trip,
        'participant': participant,
        'existing_signup': existing_signup,
        'leader_signup_allowed': leader_signup_allowed(trip, participant),
    }

    if trip.signups_open or context['leader_signup_allowed']:
        context['signup_form'] = SignUpForm(initial={'trip': trip})
        context['signup_form'].fields['trip'].widget = HiddenInput()

    return context


@register.inclusion_tag('for_templatetags/drop_off_trip.html')
def drop_off_trip(trip, existing_signup):
    return {'trip': trip, 'existing_signup': existing_signup}


@register.inclusion_tag('for_templatetags/signup_table.html')
def signup_table(signups, has_notes=False, show_drivers=False, all_participants=None):
    """ Display a table of signups (either leaders or participants).

    The all_participants argument is especially useful for including leaders
    who do not have a signup object associated with them (e.g. the people who created
    the trip, or a chair who added themselves directly by editing the trip)
    """
    # If there are participants not included in the signup list, put these
    # participants in the front of the list
    if all_participants:
        signed_up = {signup.participant.id for signup in signups}
        no_signup = all_participants.exclude(id__in=signed_up)
        fake_signups = [{'participant': leader} for leader in no_signup]
        signups = chain(fake_signups, signups)
    return {'signups': signups, 'has_notes': has_notes,
            'show_drivers': show_drivers}


@register.inclusion_tag('for_templatetags/editable_signup_table.html')
def editable_signup_table(formset):
    return {'formset': formset}


@register.inclusion_tag('for_templatetags/trip_summary.html', takes_context=True)
def trip_summary(context, trip):
    return {'show_emails': context['user'].is_authenticated, 'trip': trip}


@register.inclusion_tag('for_templatetags/medical_table.html')
def medical_table(participants):
    return {'participants': participants}


@register.inclusion_tag('for_templatetags/driver_table.html')
def driver_table(cars):
    return {'cars': cars}


@register.filter
def subtract(value, arg):
    return value - arg


@register.inclusion_tag('for_templatetags/not_on_trip.html')
def not_on_trip(trip, signups_on_trip, signups_off_trip, display_notes):
    """ Display a table of participants who're not on the given trip.

    Handles displaying all participants who were:
        1. Interested in a lottery trip
        2. Not given a slot on a FCFS trip or its waiting list
    """
    display_table = signups_on_trip or signups_off_trip

    # If all signups were placed on the trip, no sense displaying this table
    if trip.algorithm == 'fcfs' and not signups_off_trip:
        display_table = False

    return {'trip': trip,
            'signups_on_trip': signups_on_trip,
            'signups_off_trip': signups_off_trip,
            'display_table': display_table, 'display_notes': display_notes}
