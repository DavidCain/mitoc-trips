from collections.abc import Callable, Collection
from functools import wraps

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import resolve_url
from django.urls import reverse, reverse_lazy

import ws.utils.perms as perm_utils
from ws import enums
from ws.middleware import RequestWithParticipant
from ws.utils.models import problems_with_profile


def chairs_only() -> Callable:
    groups = {perm_utils.chair_group(activity_enum) for activity_enum in enums.Activity}
    return group_required(groups)


def profile_needs_update(request: RequestWithParticipant) -> bool:
    """Return if we need to redirect to 'edit_profile' for changes."""
    if not request.user.is_authenticated:
        return False  # We can't be sure until the user logs in

    return any(problems_with_profile(request.participant))


def participant_required(view_func: Callable) -> Callable:
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.participant:
            return view_func(request, *args, **kwargs)

        next_url = None
        if request.user.is_authenticated:
            next_url = resolve_url(reverse("edit_profile"))

        path = request.get_full_path()  # All requests share scheme & netloc
        return redirect_to_login(path, next_url, REDIRECT_FIELD_NAME)

    return _wrapped_view


def group_required(
    group_names: str | Collection[str],
    *,
    # A URL to redirect to after which the user _should_ have permissions
    # Be careful about redirect loops here!
    redir_url: str | None = None,
    # If the user is anonymous, allow them to view the page anyway
    allow_anonymous: bool = False,
    allow_superusers: bool = True,
) -> Callable:
    """Requires the user to belong to at least one of the Django groups.

    If the user does not belong to any of these groups and `redir_url` is
    specified, redirect them to that URL so that they may attempt again.
    A good example of this is user_info_required - participants should be
    given the chance to supply user info and successfully redirect after.
    """
    allowed_groups = (group_names) if isinstance(group_names, str) else group_names

    def in_groups(user):
        if perm_utils.in_any_group(user, allowed_groups, allow_superusers):
            return True
        if not redir_url:  # No possible way to gain access, so 403
            raise PermissionDenied
        return False

    # This is a simplified version of the user_passes_test decorator
    # We extended it to allow `redir_url` to depend on authentication
    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if allow_anonymous and not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            if profile_needs_update(request):
                next_url = resolve_url(reverse("edit_profile"))
            elif request.user.is_authenticated and in_groups(request.user):
                return view_func(request, *args, **kwargs)
            else:  # Either logged in & missing groups, or not logged in
                next_url = None

            path = request.get_full_path()  # All requests share scheme & netloc
            return redirect_to_login(path, next_url, REDIRECT_FIELD_NAME)

        return _wrapped_view

    return decorator


user_info_required = group_required(
    "users_with_info",
    allow_superusers=False,
    redir_url=reverse_lazy("edit_profile"),
)
participant_or_anon = group_required(
    "users_with_info",
    allow_superusers=False,
    allow_anonymous=True,
    redir_url=reverse_lazy("edit_profile"),
)

admin_only = user_passes_test(
    lambda u: u.is_superuser,
    login_url=reverse_lazy("account_login"),
)
