from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/show_wimp.html')
def show_wimp(wimp):
    return {
        'participant': wimp,
    }
