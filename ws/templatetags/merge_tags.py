from django import template

register = template.Library()


@register.inclusion_tag("for_templatetags/merge_pair.html")
def merge_pair(old, new):
    return {"participants": [old, new], "old": old, "new": new}
