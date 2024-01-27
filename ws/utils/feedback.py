from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from ws import models

FEEDBACK_WINDOW = timedelta(days=365 + 30)  # approximately 13 months


def feedback_cutoff() -> datetime:
    return timezone.now() - FEEDBACK_WINDOW


def without_old_feedback(
    feedback: QuerySet[models.Feedback],
) -> QuerySet[models.Feedback]:
    return feedback.exclude(time_created__lte=feedback_cutoff())


# Expose a simple helper for pre-fetched querysets!
def feedback_is_recent(feedback: models.Feedback) -> bool:
    return feedback.time_created > feedback_cutoff()
