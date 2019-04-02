from django.template import Context, Template
from django.test import SimpleTestCase


class GeneralTagsTests(SimpleTestCase):
    def test_subtract(self):
        context = Context({'number': 37})
        template_to_render = Template('{% load general_tags %}{{ number|subtract:12 }}')
        rendered_template = template_to_render.render(context)
        self.assertEqual('25', rendered_template)

    def test_strip_empty_lines(self):
        context = Context({'number': 37})
        lines = [
            '{% load general_tags %}',
            'still newlines here',
            '{% gapless %}',
            '{{ number|subtract:12 }}',  # 25, this works with tags!
            '{% if True %}',
            '  hello  ',
            '{% endif %}',
            '',
            '',  # Empty lines stripped
            '{% endgapless %}',
        ]
        template_to_render = Template('\n'.join(lines))
        rendered_template = template_to_render.render(context)
        self.assertEqual(rendered_template, '\nstill newlines here\n25\n  hello')
