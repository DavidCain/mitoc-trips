from django.test import TestCase

from ws.tests import factories


class FeedbackTest(TestCase):
    def test_str(self):
        feedback = factories.FeedbackFactory.build(
            leader__name="Janet Yellin",
            participant__name="Jerome Powell",
            comments="Shows promise",
        )
        self.assertEqual(str(feedback), 'Jerome Powell: "Shows promise" - Janet Yellin')
