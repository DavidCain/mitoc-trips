import random
import re

from django import template
from django.template.base import Node
from django.utils.functional import keep_lazy

register = template.Library()


@keep_lazy(str)
def strip_empty_lines(value):
    """Return the given HTML with empty and all-whitespace lines removed."""
    return re.sub(r"\n[ \t]*(?=\n)", "", value)


@register.tag
def gapless(parser, token):
    """Remove blank lines between `{% gapless %}` and `{% endgapless %}`"""
    nodelist = parser.parse(("endgapless",))
    parser.delete_first_token()
    return GaplessNode(nodelist)


class GaplessNode(Node):
    """Closely modeled after: https://djangosnippets.org/snippets/569/"""

    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        stripped = self.nodelist.render(context)
        stripped = strip_empty_lines(self.nodelist.render(context))
        # Strip the excess newlines from the `gapless' and `endgapless` tags being on newlines
        # (but do not strip leading space on actual lines)
        return stripped.strip("\n")


@register.filter
def subtract(value, arg):
    return value - arg


@register.filter
def scramble(text: str) -> str:
    """Reorder the characters in the text so as be not easily read by humans.

    This is *not* meant to be a cipher, the goal is simply to make the text
    appear scrambled (we'll apply a Gaussian blur atop the text too). Because
    HTML strips extra spaces, we ideally want to take care to avoid:

    - leading spaces
    - trailing spaces
    - double spaces between "words"
    """
    return "".join(random.sample(text, len(text)))
