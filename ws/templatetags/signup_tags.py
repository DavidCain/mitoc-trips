from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/signup_table.html')
def signup_table(signups, has_notes=False):
    return {'signups': signups, 'has_notes': has_notes}


@register.inclusion_tag('for_templatetags/editable_signup_table.html')
def editable_signup_table(formset):
    return {'formset': formset}


@register.inclusion_tag('for_templatetags/trip_summary.html')
def trip_summary(trip):
    return {'trip': trip}
