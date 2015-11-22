from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse_lazy

from ws import perm_utils


#NOTE: Currently excludes the WSC (only the WS chair can assign ratings)
def chairs_only(*activity_types, **kwargs):
    if not activity_types:
        activity_types = perm_utils.activity_types
    groups = {perm_utils.chair_group(activity) for activity in activity_types}
    return group_required(*groups, **kwargs)

def group_required(*group_names, **kwargs):
    """ Requires user membership in at least one of the groups passed in. """
    # Adapted from Django snippet #1703
    login_url = kwargs.get('login_url', None)
    def in_groups(user):
        allow_superusers = kwargs.get('allow_superusers', True)
        if perm_utils.in_any_group(user, group_names, allow_superusers):
            return True
        if not login_url:
            raise PermissionDenied()
    return user_passes_test(in_groups, login_url=login_url)


user_info_required = group_required('users_with_info', allow_superusers=False,
                                    login_url=reverse_lazy('update_info'))

admin_only = user_passes_test(lambda u: u.is_superuser,
                              login_url=reverse_lazy('admin:login'))
