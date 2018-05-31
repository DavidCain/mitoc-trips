from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/active_discounts.html')
def active_discounts(participant):
    return {'participant': participant}
