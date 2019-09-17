import logging

from django.contrib import messages
from django.urls import reverse

from . import MessageGenerator

logger = logging.getLogger(__name__)


class Messages(MessageGenerator):
    def supply(self):
        """ Warn if the participant's password is insecure.

        When a participant logs in with a known insecure password, they are
        redirected to the "change password" page. They *should* change their
        password immediately, but we don't mandate a password change before they can
        use the rest of the site.

        We *might* require an immediate password change in the future, but for now
        there are good reasons not to (for example, a participant is out on a
        weekend trip and needs to log in to access important trip information, but
        cannot easily generate a strong password with just their mobile device).

        This serves to warn people who ignore the message (and log that they ignored it,
        so we might use that data to inform a better password policy).
        """
        change_password_url = reverse('account_change_password')
        if self.request.path == change_password_url:
            # Already on the 'change password' URL, no need to warn again
            return

        par = self.request.participant
        if par and par.insecure_password:
            msg = (
                'Your password is insecure! '
                f'Please <a href="{change_password_url}">change your password.</a>'
            )
            warned = self.add_unique_message(messages.ERROR, msg, extra_tags='safe')

            if warned:
                logger.info(
                    "Warned participant %s (%s) about insecure password",
                    par.pk,
                    par.email,
                )
