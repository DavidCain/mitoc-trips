from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/signup_table.html')
def signup_table(signups, has_notes=False, show_drivers=False):
    return {'signups': signups, 'has_notes': has_notes,
            'show_drivers': show_drivers}


@register.inclusion_tag('for_templatetags/participant_table.html')
def participant_table(participants, show_drivers=False):
    return {'participants': participants, 'show_drivers': show_drivers}


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
