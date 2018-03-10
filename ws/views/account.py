"""
Views relating to account management.
"""
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy

from allauth.account.views import PasswordChangeView


class LoginAfterPasswordChangeView(PasswordChangeView):
    @property
    def success_url(self):
        return reverse_lazy('account_login')


# TODO: Just decorate dispatch!?
login_after_password_change = login_required(LoginAfterPasswordChangeView.as_view())
