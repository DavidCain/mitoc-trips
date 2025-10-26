from django.template import Context, Template
from django.test import SimpleTestCase

from ws.tests import factories


class FormatPhoneNumberTest(SimpleTestCase):
    def test_format_blank_phone_number(self) -> None:
        html_template = Template(
            "{% load misc_tags %}{{ par.cell_phone|format_phone_number }}"
        )
        context = Context({"par": factories.ParticipantFactory.build(cell_phone="")})
        self.assertFalse(html_template.render(context))

    def test_format_us_phone_number(self) -> None:
        html_template = Template(
            "{% load misc_tags %}{{ par.cell_phone|format_phone_number }}"
        )
        context = Context(
            {"par": factories.ParticipantFactory.build(cell_phone="+16175551234")}
        )
        self.assertEqual(html_template.render(context), "(617) 555-1234")

    def test_international_phone_number(self) -> None:
        html_template = Template(
            "{% load misc_tags %}{{ par.cell_phone|format_phone_number }}"
        )
        context = Context(
            {"par": factories.ParticipantFactory.build(cell_phone="+33700555740")}
        )
        self.assertEqual(html_template.render(context), "+33 7 00 55 57 40")


class RedactTest(SimpleTestCase):
    def test_should_redact(self) -> None:
        html_template = Template(
            "{% load misc_tags %}Secret identity: {{ name|redact:hide_name }}"
        )
        context = Context({"name": "Bruce Wayne", "hide_name": True})
        self.assertEqual(
            html_template.render(context), "Secret identity: <em>redacted</em>"
        )

    def test_should_not_redact(self) -> None:
        html_template = Template("{% load misc_tags %}{{ name|redact:hide_name }}")
        context = Context({"name": "Jacques Clouseau", "hide_name": False})
        self.assertEqual(html_template.render(context), "Jacques Clouseau")
