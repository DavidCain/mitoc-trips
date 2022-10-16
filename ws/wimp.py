from django.db.models.expressions import RawSQL

from ws import models


def active_wimps():
    """Return all Participants that are currently WIMPs.

    Generally speaking, we should have only one WIMP, but we should handle the
    case of there being more than one, since the data model supports that.
    """
    return models.Participant.objects.filter(user__groups__name='WIMP').order_by(
        RawSQL('auth_user_groups.id', ()).desc()
    )


def current_wimp() -> models.Participant | None:
    return active_wimps().first()
