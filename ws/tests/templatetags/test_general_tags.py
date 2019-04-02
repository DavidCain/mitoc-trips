from django.template import Context, Template
from django.test import SimpleTestCase


class GeneralTagsTests(SimpleTestCase):
    def test_subtract(self):
        context = Context({'number': 37})
        template_to_render = Template('{% load general_tags %}{{ number|subtract:12 }}')
        rendered_template = template_to_render.render(context)
        self.assertEqual('25', rendered_template)
