from django.core.exceptions import ObjectDoesNotExist
from ws import models


class ParticipantMiddleware(object):
    """ On pretty much every view, we will check the user's:

        - Participant object
        - Leader status
        - Groups

        To reduce query counts, bake all of this into the core query that
        generates the user.
    """
    def process_request(self, request):
        user = request.user
        if user.is_anonymous():
            request.participant = None

        try:
            request.participant = models.Participant.objects.get(user_id=user.id)
        except ObjectDoesNotExist:
            request.participant = None
