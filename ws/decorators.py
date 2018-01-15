import base64
import hashlib
import hmac
from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.views import redirect_to_login
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import JsonResponse
from django.shortcuts import resolve_url
from django.utils.decorators import available_attrs
from django.utils.html import escape

import ws.utils.perms


def chairs_only(*activity_types, **kwargs):
    if not activity_types:
        activity_types = ws.utils.perms.activity_types
    groups = {ws.utils.perms.chair_group(activity) for activity in activity_types}
    return group_required(*groups, **kwargs)


def profile_needs_update(request):
    """ Return if the user's profile is missing or in need of correction.

    Create messages indicating the required changes so that the user may
    correct them.
    """
    if request.user.is_anonymous():
        return False  # We can't be sure until the user logs in

    par = request.participant
    if not par:
        return True

    has_problems = False

    if not par.emergency_info.emergency_contact.cell_phone:
        messages.info(request, "Please supply a valid number for your emergency contact.")
        has_problems = True
    if ' ' not in par.name:
        messages.info(request, "Please supply your full legal name.")
        has_problems = True

    emails = request.user.emailaddress_set
    if not emails.filter(email=par.email, verified=True).exists():
        messages.info(request,
                      'Please <a href="{}">'.format(reverse('account_email')) +
                      'verify that you own {}</a>, or set your system '
                      'email address to one of your already verified email '
                      'addresses.'.format(escape(par.email)),
                      extra_tags='safe')
        has_problems = True

    if len(par.affiliation) == 1:
        messages.info(request, 'Please update your MIT affiliation.')
        has_problems = True

    return has_problems


def group_required(*group_names, **kwargs):
    """ Requires user membership in at least one of the groups passed in.

    If the user does not belong to any of these groups and `redir_url` is
    specified, redirect them to that URL so that they may attempt again.
    A good example of this is user_info_required - participants should be
    given the chance to supply user info and successfully redirect after.
    """
    # A URL to redirect to after which the user _should_ have permissions
    # Be careful about redirect loops here!
    redir_url = kwargs.get('redir_url', None)

    def in_groups(user):
        allow_superusers = kwargs.get('allow_superusers', True)
        if ws.utils.perms.in_any_group(user, group_names, allow_superusers):
            return True
        if not redir_url:  # No possible way to gain access, so 403
            raise PermissionDenied()

    # This is a simplified version of the user_passes_test decorator
    # We extended it to allow `redir_url` to depend on authentication
    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            logged_in = request.user.is_authenticated()

            if profile_needs_update(request):
                next_url = resolve_url(reverse('edit_profile'))
            elif logged_in and in_groups(request.user):
                return view_func(request, *args, **kwargs)
            else:  # Either logged in & missing groups, or not logged in
                next_url = None

            path = request.get_full_path()  # All requests share scheme & netloc
            return redirect_to_login(path, next_url, REDIRECT_FIELD_NAME)
        return _wrapped_view
    return decorator


def membership_signature_valid(view_func):
    """ The request is verified as from the membership processing pipeline. """
    def decorator(request, *args, **kwargs):
        # No need for JWT - we're only signing a single attribute
        # and Python comes built in with HMAC support. Keep it simple.
        if not (request.GET.get('email') and request.GET.get('signature')):
            return JsonResponse({'message': 'email or signature missing'}, status=401)

        email = request.GET['email'].encode('utf-8')
        signature = request.GET['signature'].encode('utf-8')
        key = settings.MEMBERSHIP_SECRET_KEY
        msg_hmac = hmac.new(key.encode('utf-8'), email, hashlib.sha256)
        signed = base64.b64encode(msg_hmac.digest())

        if signature == signed:
            return view_func(request, *args, **kwargs)
        else:
            return JsonResponse({'message': 'invalid signature'}, status=401)
    return decorator


user_info_required = group_required('users_with_info', allow_superusers=False,
                                    redir_url=reverse_lazy('edit_profile'))

admin_only = user_passes_test(lambda u: u.is_superuser,
                              login_url=reverse_lazy('account_login'))
