import logging

from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from django.http import HttpRequest

from ws import settings

logger = logging.getLogger(__name__)


class TrustGoogleEmailOwnershipAdapter(DefaultSocialAccountAdapter):
    """Let users with an existing account grant Google login access.

    This adapter exists to provide a better UX in the following scenario:

    1. `alice@gmail.com` signs up for `mitoc-trips` with a email & password
    2. Alice signs out, time passes.
    3. Later, Alice "logs in with Google"
    4. Because an account exists under `alice@gmail.com`, we can't complete login
        - Alice must first log in with her password, then associate Google

    By default, `django-allauth` will not let you automatically claim ownership
    of an account just because a social provider vouches that you exist under
    that email address. This makes sense. If you own a Facebook account under
    `alice@gmail.com`, there's no guarantees that you're necessarily the same
    person.

    However, because Google is an email provider, I think it's fair to assume
    that if Google vouches for your identity, auto sign-in can be completed.

    Related: https://github.com/pennersr/django-allauth/issues/418
    """

    def pre_social_login(self, request: HttpRequest, sociallogin: SocialLogin) -> None:
        """Connect any Google-asserted email to accounts if existing."""
        if sociallogin.is_existing:  # Social account exists (normal login)
            return

        # I don't think there's an easy way to identify the provider in use...
        # `request.path` should be at least be '/accounts/google/login/callback/'
        assert set(settings.SOCIALACCOUNT_PROVIDERS) == {'google'}

        email: str = user_email(sociallogin.user)

        try:
            verified_email = EmailAddress.objects.get(
                email__iexact=email,
                # This is critical. If we didn't require a *verified* email, then
                # we could end up linking this to an existing account which belongs
                # to a malicious user hoping that somebody will link their Google account.
                verified=True,
            )
        except EmailAddress.DoesNotExist:
            return

        sociallogin.connect(request, verified_email.user)
