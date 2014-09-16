from django import template

register = template.Library()


def signup_table(signups, has_notes=False):
    return {'signups': signups, 'has_notes': has_notes}

register.inclusion_tag('signup_table.html')(signup_table)
