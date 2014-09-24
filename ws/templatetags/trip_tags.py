from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/trip_list_table.html')
def trip_list_table(trip_list):
    return {'trip_list': trip_list}
