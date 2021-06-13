from functools import wraps
from typing import Optional

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import resolve_url
from django.urls import reverse, reverse_lazy
from django.utils.decorators import available_attrs

import ws.utils.perms as perm_utils
from ws import enums
from ws.utils.models import problems_with_profile


def chairs_only():
    groups = {perm_utils.chair_group(activity_enum) for activity_enum in enums.Activity}
    return group_required(*groups)


def profile_needs_update(request):
    """Return if we need to redirect to 'edit_profile' for changes."""
    if not request.user.is_authenticated:
        return False  # We can't be sure until the user logs in

    return any(problems_with_profile(request.participant))


def participant_required(view_func):
    @wraps(view_func, assigned=available_attrs(view_func))
    def _wrapped_view(request, *args, **kwargs):
        if request.participant:
            return view_func(request, *args, **kwargs)

        next_url: Optional[str] = None
        if request.user.is_authenticated:
            next_url = resolve_url(reverse('edit_profile'))

        path = request.get_full_path()  # All requests share scheme & netloc
        return redirect_to_login(path, next_url, REDIRECT_FIELD_NAME)

    return _wrapped_view


def group_required(*group_names, **kwargs):
    """Requires user membership in at least one of the groups passed in.

    If the user does not belong to any of these groups and `redir_url` is
    specified, redirect them to that URL so that they may attempt again.
    A good example of this is user_info_required - participants should be
    given the chance to supply user info and successfully redirect after.
    """
    # A URL to redirect to after which the user _should_ have permissions
    # Be careful about redirect loops here!
    redir_url = kwargs.get('redir_url', None)

    # If the user is anonymous, allow them to view the page anyway
    allow_anonymous = kwargs.get('allow_anonymous', False)

    def in_groups(user):
        allow_superusers = kwargs.get('allow_superusers', True)
        if perm_utils.in_any_group(user, group_names, allow_superusers):
            return True
        if not redir_url:  # No possible way to gain access, so 403
            raise PermissionDenied
        return False

    # This is a simplified version of the user_passes_test decorator
    # We extended it to allow `redir_url` to depend on authentication
    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            if allow_anonymous and not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            if profile_needs_update(request):
                next_url: Optional[str] = resolve_url(reverse('edit_profile'))
            elif request.user.is_authenticated and in_groups(request.user):
                return view_func(request, *args, **kwargs)
            else:  # Either logged in & missing groups, or not logged in
                next_url = None

            path = request.get_full_path()  # All requests share scheme & netloc
            return redirect_to_login(path, next_url, REDIRECT_FIELD_NAME)

        return _wrapped_view

    return decorator


user_info_required = group_required(
    'users_with_info', allow_superusers=False, redir_url=reverse_lazy('edit_profile')
)
participant_or_anon = group_required(
    'users_with_info',
    allow_superusers=False,
    allow_anonymous=True,
    redir_url=reverse_lazy('edit_profile'),
)

admin_only = user_passes_test(
    lambda u: u.is_superuser, login_url=reverse_lazy('account_login')
)
