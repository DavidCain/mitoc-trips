from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse_lazy


def group_required(*group_names, **kwargs):
    """ Requires user membership in at least one of the groups passed in. """
    # Adapted from Django snippet #1703
    login_url = kwargs.get('login_url', None)
    def in_groups(u):
        if u.is_authenticated():
            if bool(u.groups.filter(name__in=group_names)) | u.is_superuser:
                return True
        if not login_url:
            raise PermissionDenied()
    return user_passes_test(in_groups, login_url=login_url)


user_info_required = group_required('users_with_info',
                                    login_url=reverse_lazy('update_info'))

admin_only = user_passes_test(lambda u: u.is_superuser,
                              login_url=reverse_lazy('admin:login'))
