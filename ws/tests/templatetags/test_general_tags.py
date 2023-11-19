import random

from django.template import Context, Template
from django.test import SimpleTestCase


class GeneralTagsTests(SimpleTestCase):
    def test_subtract(self):
        context = Context({"number": 37})
        template_to_render = Template("{% load general_tags %}{{ number|subtract:12 }}")
        rendered_template = template_to_render.render(context)
        self.assertEqual("25", rendered_template)

    def test_strip_empty_lines(self):
        context = Context({"number": 37})
        lines = [
            "{% load general_tags %}",
            "still newlines here",
            "{% gapless %}",
            "{{ number|subtract:12 }}",  # 25 (this works with tags)!
            "{% if True %}",
            '  {% if "string_is_truthy" %}',
            "    hello  ",  # leading & trailing whitespace not touched.
            "  {% endif %}",
            "{% endif %}",
            "",
            "",  # Empty lines stripped
            "{% endgapless %}",
        ]
        template_to_render = Template("\n".join(lines))
        rendered_template = template_to_render.render(context)
        self.assertEqual(rendered_template, "\nstill newlines here\n25\n    hello  ")

    def test_scramble(self):
        random.seed("Fixed seed to get consistent scrambling")

        text = "This is a super secret sentence (not really)."
        context = Context({"text": text})
        template_to_render = Template("{% load general_tags %}{{ text|scramble }}")
        rendered_template = template_to_render.render(context)
        # The two texts should have the exact same set of characters
        self.assertEqual(sorted(rendered_template), sorted(text))

        # Because we set the random seed, it'll scramble the same way each time.
        self.assertEqual(
            "pha ectl sn.eeyse  e erosi)iasl nT(rsctetur n", rendered_template
        )
