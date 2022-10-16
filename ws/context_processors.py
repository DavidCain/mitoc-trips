import functools
import os

from ws import settings


def participant_and_groups(request):
    group_names = [group.name for group in request.user.groups.all()]
    return {'groups': group_names, 'viewing_participant': request.participant}


def angular_templates(request):
    for_caching = {} if settings.DEBUG else cached_templates()
    return {'angular_templates': for_caching}


@functools.cache
def cached_templates():
    """Cache templates so that we don't need to lead with each request."""
    return dict(get_all_angular_templates())


def get_all_angular_templates():
    """Yield the filename and contents for use in populating the cache."""
    template_dir = os.path.join(settings.STATIC_ROOT, 'template')
    for filename in os.listdir(template_dir):
        with open(os.path.join(template_dir, filename), encoding='utf-8') as handle:
            url = os.path.join(settings.STATIC_URL, 'template', filename)
            yield url, handle.read()
