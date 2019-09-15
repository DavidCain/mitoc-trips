from django.contrib import messages
from django.urls import reverse

from . import MessageGenerator


class Messages(MessageGenerator):
    def supply(self):
        """ Create message if Participant info needs update. Otherwise, do nothing. """
        if not self.request.user.is_authenticated:
            return

        participant = self.request.participant
        if not participant:  # Authenticated, but no info yet
            msg = 'Personal information missing.'
        else:
            if participant.info_current:  # Record exists, is up to date
                return
            msg = 'Personal information is out of date.'

        edit_url = reverse('edit_profile')
        msg += ' <a href="{}">Update</a> to sign up for trips.'.format(edit_url)
        messages.warning(self.request, msg, extra_tags='safe')
