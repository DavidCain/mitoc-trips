import markdown2

from django.utils.safestring import mark_safe
from django import template

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text):
    return mark_safe(markdown2.markdown(text, safe_mode="escape"))
