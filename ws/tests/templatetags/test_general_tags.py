import time
import unittest

from django.template import Context, Template
from django.test import SimpleTestCase

from ws.templatetags import general_tags


class GeneralTagsTests(SimpleTestCase):
    def tearDown(self):
        general_tags.SCRAMBLER.seed(time.time())  # Don't leak seed to other tests

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
        general_tags.SCRAMBLER.seed("Fixed seed to get consistent scrambling")

        text = "This is a super secret sentence (not really)."
        context = Context({"text": text})
        template_to_render = Template("{% load general_tags %}{{ text|scramble }}")
        rendered_template = template_to_render.render(context)
        # The two texts should have the exact same set of characters
        self.assertEqual(sorted(rendered_template), sorted(text))

        # Because we set the random seed, it'll scramble the same way each time.
        self.assertEqual(
            "shus tt l iraca (.ysti prneerT) csns eeloneee", rendered_template
        )


class ScrambleTest(unittest.TestCase):
    def setUp(self):
        general_tags.SCRAMBLER.seed("Fixed seed to get consistent scrambling")

    def tearDown(self):
        general_tags.SCRAMBLER.seed(time.time())  # Don't leak seed to other tests

    def assertScrambles(self, raw: str, scrambled: str) -> None:  # noqa: N802
        self.assertEqual(
            general_tags.scramble(raw),
            scrambled,
        )

    def test_leading_spaces(self):
        self.assertScrambles(
            "  Weird, feedback should be stripped.",
            "  sfWpdt rdbsbria edihpe el ceuk.,edo",
        )

    def test_trailing_spaces(self):
        self.assertScrambles(
            "  Weird, feedback should be stripped.    \n",
            "  sfWpdt rdbsbria edihpe el ceuk.,edo    \n",
        )

    def test_extra_spaces_between_words(self):
        self.assertScrambles(
            "What's         up?",
            "tWuhp?         s'a",
        )

    def test_lots_of_whitespace(self):
        self.assertScrambles(
            "  Who\t  would write\n  feedback like\r this?",
            "  ilW\t  okwck eieot\n  lstehhwa edbf\r ?uird",
        )

    def test_right_to_left_unicode(self):
        self.assertScrambles(
            "هل تتحدث العربية",
            "بت هتلاد ةثريلحع",
        )

    def test_unicode_spaces(self):
        self.assertScrambles(
            "You\u2004Fancy, huh?\u2008",  # THREE-PER-EM SPACE, PUNCTUATION SPACE
            "hFY\u2004uoyhun c?,a\u2008",
        )
