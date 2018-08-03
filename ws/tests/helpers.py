from django.contrib.auth.models import Group


class PermHelpers:
    @staticmethod
    def mark_leader(user):
        """ Mark the user as belonging to the leaders group.

        Note that some views may expect a LeaderRating to be present for the
        user's Participant object. This is sufficient to pass access control, though.
        """
        leaders = Group.objects.get(name='leaders')
        leaders.user_set.add(user)

    @staticmethod
    def mark_participant(user):
        """ Mark the user as having participation information.

        Note that this may not be enough to allow access to participant-only
        pages. In the cases of bad phone numbers, non-verified emails, or any
        other state of dated participation info, users will still be rediricted
        to update their information.

        To disable this redirect, mock `ws.decorators.profile_needs_update`
        """
        users_with_info = Group.objects.get(name='users_with_info')
        users_with_info.user_set.add(user)
