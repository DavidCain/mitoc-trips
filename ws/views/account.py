"""
Views relating to account management.
"""
from allauth.account.views import PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.decorators import method_decorator


class LoginAfterPasswordChangeView(PasswordChangeView):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    @property
    def success_url(self):
        return reverse('account_login')
