from django.db.models import Case, F, IntegerField, Q, When


def annotate_reciprocally_paired(participants):
    """ Annotate a QuerySet of participants to indicate if bidirectionally paired. """
    is_reciprocally_paired = Q(
        pk=F('lotteryinfo__paired_with__lotteryinfo__paired_with__pk')
    )

    return participants.annotate(
        # Django 2.0: Use conditional aggregation instead!
        reciprocally_paired=Case(
            When(is_reciprocally_paired, then=1), default=0, output_field=IntegerField()
        )
    )
