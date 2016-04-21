from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/simple_trip_list.html')
def simple_trip_list(trip_list, max_title_chars=45, max_description_chars=120):
    return {'trip_list': trip_list,
            'max_title_chars': max_title_chars,
            'max_description_chars': max_description_chars}

@register.inclusion_tag('for_templatetags/trip_list_table.html')
def trip_list_table(trip_list):
    return {'trip_list': trip_list}

@register.filter
def name_with_activity(leader, activity):
    return leader.name_with_rating(activity)

@register.filter
def activity_rating(leader, activity):
    return leader.activity_rating(activity) or ""
