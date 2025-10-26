from django.test import TestCase

from ws.tests import factories


class LotteryInfoTest(TestCase):
    def test_recipricoally_paired_with_nobody(self) -> None:
        info = factories.LotteryInfoFactory.create(paired_with=None)
        self.assertFalse(info.reciprocally_paired_with)

    def test_not_saved_yet(self) -> None:
        """Handles the case of not being saved yet, where it has a null PK."""
        par = factories.ParticipantFactory.build()
        other = factories.ParticipantFactory.build()
        info = factories.LotteryInfoFactory.build(participant=par, paired_with=other)
        self.assertFalse(info.reciprocally_paired_with)

    def test_not_reciprocated(self) -> None:
        par = factories.ParticipantFactory.create()
        other = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=other, paired_with=None)

        info = factories.LotteryInfoFactory.create(participant=par, paired_with=other)
        self.assertFalse(info.reciprocally_paired_with)

    def test_reciprocally_paired_with(self) -> None:
        bert = factories.ParticipantFactory.create()
        ernie = factories.ParticipantFactory.create()

        bert_info = factories.LotteryInfoFactory.create(
            participant=bert, paired_with=ernie
        )

        self.assertFalse(bert_info.reciprocally_paired_with)

        # Neither is reciprocally paired, even when Ernie has info
        ernie_info = factories.LotteryInfoFactory.create(
            participant=ernie, paired_with=None
        )
        self.assertFalse(bert_info.reciprocally_paired_with)
        self.assertFalse(ernie_info.reciprocally_paired_with)

        # Once they both choose to pair with one another, it's reciprocal!
        ernie_info.paired_with = bert
        ernie_info.save()
        self.assertTrue(bert_info.reciprocally_paired_with)
        self.assertTrue(ernie_info.reciprocally_paired_with)
