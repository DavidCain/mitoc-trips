from itertools import chain

from django import template

register = template.Library()


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


@register.inclusion_tag('for_templatetags/trip_summary.html')
def trip_summary(trip):
    return {'trip': trip}


@register.inclusion_tag('for_templatetags/medical_table.html')
def medical_table(participants):
    return {'participants': participants}


@register.inclusion_tag('for_templatetags/driver_table.html')
def driver_table(cars):
    return {'cars': cars}


@register.filter
def subtract(value, arg):
    return value - arg
