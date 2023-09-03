"""
Views relating to account management.
"""
import logging
from urllib.parse import urlencode

from allauth.account.forms import LoginForm
from allauth.account.views import LoginView, PasswordChangeView
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator

from ws import models
from ws.auth import times_seen_in_hibp
from ws.utils.dates import local_now

logger = logging.getLogger(__name__)


class CustomPasswordChangeView(PasswordChangeView):
    """Custom password change view that makes two key changes:

    1. Redirects to login immediately after changing password
       (prevents an endless loop inherent in django-allaauth)
    2. Marks password as "not pwned" since validation has passed
        - It's possible that the API was down at the time, and we had to fall
          back to using Django's password validator instead. However, it's still
          acceptable to marked the password "not pwned" since:
            - To keep the password marked as "pwned" locks out users
            - We will perform another check on the next login
    """

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @property
    def success_url(self):
        return reverse('account_login')

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.participant:
            models.PasswordQuality.objects.update_or_create(
                participant=self.request.participant,
                defaults={
                    'is_insecure': False,
                    # NOTE: Technically, we cannot know for sure if the API call to HIBP failed
                    # (and thus, we might be updating this timestamp incorrectly)
                    # However, we log API failures and could use that information to identify the last success.
                    'last_checked': local_now(),
                },
            )
        return response


class CheckIfPwnedOnLoginView(LoginView):
    """Whenever users log in, we should check that their password has not been compromised.

    There are two reasons to perform this check:
    - Because passwords are salted & hashed, we have no way of knowing either
      users' raw passwords (or their hashes). Login is the only time we can check
      that passwords are secure.
    - It's possible that a user's password was recently added to the database
      of breached passwords - we should check on every login.
    """

    def _form_valid_perform_login(
        self,
        form: LoginForm,
    ) -> tuple[int | None, HttpResponse]:
        """Performs login with a correct username/password.

        Returns if this password has been seen in data breaches, plus the
        appropriate HTTP response for form_valid.

        As a side effect, this populates `self.request.user`
        """
        times_seen = times_seen_in_hibp(form.cleaned_data['password'])

        if times_seen:
            change_password_url = reverse('account_change_password')

            # Make sure we preserve the original redirect, if there was one
            next_url = self.request.GET.get('next')
            if next_url:
                change_password_url += '?' + urlencode({'next': next_url})
            response = form.login(self.request, redirect_url=change_password_url)
        else:
            response = super().form_valid(form)

        return times_seen, response

    def _post_login_update_password_validity(
        self,
        times_password_seen: int | None,
    ) -> None:
        """After form.login has been invoked, handle password being breached or not.

        This method exists to serve two types of users:
        - those who have a corresponding Participant model (most active users)
        - those who have only a user record (signed up, never finished registration)
        """
        user = self.request.user
        assert user, "Method should be invoked *after* user login."

        # The user may or may not have a participant record linked!
        # If they do have a participant, set the password as insecure (or not)
        participant = models.Participant.from_user(user)
        if participant:
            quality, _created = models.PasswordQuality.objects.get_or_create(
                participant=participant
            )
            if times_password_seen is not None:  # (None indicates an API failure)
                quality.last_checked = local_now()
            quality.is_insecure = bool(times_password_seen)
            quality.save()

        if not times_password_seen:  # Password okay? Nothing more to do here.
            return

        if participant:
            logger.info(
                "Participant %s logged in with a breached password", participant.pk
            )
        else:
            logger.info("User %s logged in with a breached password", user.pk)
            # For non-new users lacking a participant (very rare), a message + redirect is fine.
            # If they ignore the reset, they'll be locked out once creating a Participant record.
            messages.error(
                self.request,
                'This password has been compromised! Please choose a new password. '
                'If you use this password on any other sites, we recommend changing it immediately.',
            )

    def form_valid(self, form):
        times_password_breached, response = self._form_valid_perform_login(form)
        self._post_login_update_password_validity(times_password_breached)

        return response
