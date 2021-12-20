from django.test import TestCase
from freezegun import freeze_time

from ws import models
from ws.tests import factories


class FeedbackTest(TestCase):
    def test_str(self):
        feedback = factories.FeedbackFactory.build(
            leader__name="Janet Yellin",
            participant__name="Jerome Powell",
            comments="Shows promise",
        )
        self.assertEqual(str(feedback), 'Jerome Powell: "Shows promise" - Janet Yellin')

    def test_bygones_be_bygones(self):
        """When querying for feedback, anything older than 13 months is ignored."""
        with freeze_time('2019-11-13 12:00 UTC'):
            old_feedback = factories.FeedbackFactory.create()

        # Just shy of 13 months elapsed (normal cutoff)
        with freeze_time('2020-12-01 12:00 UTC'):
            self.assertTrue(models.Feedback.objects.exists())

        # 13 months have passed, the feedback is now hidden.
        with freeze_time('2020-12-20 12:00 UTC'):
            self.assertFalse(models.Feedback.objects.exists())

            # New feedback, however is *not* hidden
            new_feedback = factories.FeedbackFactory.create()
            self.assertEqual(models.Feedback.objects.get().pk, new_feedback.pk)

            # Finally, we can show that both feedback objects are there.
            self.assertCountEqual(
                models.Feedback.everything.all().values_list('pk', flat=True),
                {old_feedback.pk, new_feedback.pk},
            )

    def test_ws_2022_temporary_feedback_extension(self):
        """During Winter School 2022, we show feedback from the last 25 months."""
        with freeze_time('2019-11-01 12:00 UTC'):
            factories.FeedbackFactory.create()

        with freeze_time('2020-02-01 12:00 UTC'):
            qualified_feedback = factories.FeedbackFactory.create()

        # Normally, 13 months have passed & we hide
        with freeze_time('2021-12-01 12:00 UTC'):
            self.assertFalse(models.Feedback.objects.exists())

        # During WS 2022, we show feedback < 25 months
        with freeze_time('2022-01-05 12:00 UTC'):
            only_feedback = models.Feedback.objects.get()
            self.assertEqual(only_feedback.pk, qualified_feedback.pk)

        # The 13 month rule returns afterwards, though
        with freeze_time('2022-02-05 12:00 UTC'):
            self.assertFalse(models.Feedback.objects.exists())
