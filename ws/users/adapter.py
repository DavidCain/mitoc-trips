from django.conf import settings
from allauth.account.adapter import DefaultAccountAdapter

class AllowSignupAdapter(DefaultAccountAdapter):
    """ Only allow signups if they're open. """
    def is_open_for_signup(self, request):
        return settings.SIGNUPS_OPEN
