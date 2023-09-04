from collections.abc import Callable

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse

from ws.messages import security
from ws.models import Participant


class RequestWithParticipant(HttpRequest):
    participant: Participant


class PrefetchGroupsMiddleware:
    """Prefetch the user's groups for use in the requset.

    We do a lot of group-centric logic - if the user's groups aren't
    prefetched, then we can easily have n+1 queries. This middleware
    prevents n+1 queries, at the cost of 1 extra query.

    This is a slight hack - the proper way to implement this is with
    a custom authentication backend where we implement the get_user()
    method to do the prefetching (we would obviously extend all-auth).
    For now, this cuts down on query time and execution.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            filtered_user = User.objects.filter(pk=request.user.pk)
            request.user = filtered_user.prefetch_related('groups').get()
        return self.get_response(request)


class ParticipantMiddleware:
    """Include the user's participant (used in most views)"""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # TODO: We check for `password_quality` on every request. We should join that.
        request.participant = (  # type: ignore[attr-defined]
            Participant.from_user(request.user)
        )
        return self.get_response(request)


class CustomMessagesMiddleware:
    """Render some custom messages on every page load.

    Caution: *must* be installed after both:
    - ParticipantMiddleware (to access participant info for messages)
    - MessagesMiddleware (to render messages)
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        security.Messages(request).supply()
        return self.get_response(request)
