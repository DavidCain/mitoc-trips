from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from ws import models


class PrefetchGroupsMiddleware(object):
    """ Prefetch the user's groups for use in the requset.

    We do a lot of group-centric logic - if the user's groups aren't
    prefetched, then we can easily have n+1 queries. This middleware
    prevents n+1 queries, at the cost of 1 extra query.

    This is a slight hack - the proper way to implement this is with
    a custom authentication backend where we implement the get_user()
    method to do the prefetching (we would obviously extend all-auth).
    For now, this cuts down on query time and execution.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            filtered_user = User.objects.filter(pk=request.user.pk)
            request.user = filtered_user.prefetch_related('groups').get()
        return self.get_response(request)


class ParticipantMiddleware(object):
    """ Include the user's participant (used in most views) """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_anonymous:
            request.participant = None
        else:
            try:
                request.participant = models.Participant.objects.get(user_id=user.id)
            except ObjectDoesNotExist:
                request.participant = None
        return self.get_response(request)
