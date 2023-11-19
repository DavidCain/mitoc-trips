from django.contrib import messages
from django.urls import reverse

from ws.utils.models import problems_with_profile

from . import MessageGenerator


class Messages(MessageGenerator):
    def supply(self):
        """Create message if Participant info needs update. Otherwise, do nothing."""
        if not self.request.user.is_authenticated:
            return

        if any(problems_with_profile(self.request.participant)):
            edit_url = reverse("edit_profile")
            self.add_unique_message(
                messages.WARNING,
                f'<a href="{edit_url}">Update your profile</a> to sign up for trips.',
                extra_tags="safe",
            )
