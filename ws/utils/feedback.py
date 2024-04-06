from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.db.models.fields import DateField
from django.db.models.functions import Cast, Least
from django.utils import timezone

from ws import models

FEEDBACK_WINDOW = timedelta(days=365 + 30)  # approximately 13 months


def feedback_cutoff() -> datetime:
    return timezone.now() - FEEDBACK_WINDOW


def for_feedback_table_display(
    feedback: QuerySet[models.Feedback],
    *,
    viewing_participant: models.Participant,
) -> QuerySet[models.Feedback]:
    return (
        # Sanity check -- *always* exclude feedback given for the participant.
        # This really only applies when activity chairs view their own applications.
        feedback.exclude(participant=viewing_participant)
        .select_related("leader", "trip")
        .prefetch_related("leader__leaderrating_set")
        .annotate(
            display_date=Least("trip__trip_date", Cast("time_created", DateField()))
        )
        .order_by("-display_date", "-time_created")
    )


def without_old_feedback(
    feedback: QuerySet[models.Feedback],
) -> QuerySet[models.Feedback]:
    return feedback.exclude(time_created__lte=feedback_cutoff())


# Expose a simple helper for pre-fetched querysets!
def feedback_is_recent(feedback: models.Feedback) -> bool:
    return feedback.time_created > feedback_cutoff()
