from django import template

register = template.Library()


def signup_table(signups, has_notes=False):
    return {'signups': signups, 'has_notes': has_notes}

def trip_summary(trip):
    return {'trip': trip}

register.inclusion_tag('signup_table.html')(signup_table)
register.inclusion_tag('trip_summary.html')(trip_summary)
