from django import template
from django.utils.safestring import mark_safe

from ws.utils.avatar import avatar_url

register = template.Library()


@register.filter
def avatar_square(participant, size=30):
    return avatar(participant, size, False)


@register.filter
def avatar(participant, size=40, img_rounded=True):
    kwargs = {
        "url": avatar_url(participant, size),
        "size": size,
        "class": 'class="img-rounded"' if img_rounded else "",
    }
    return mark_safe(  # noqa: S308
        '<img {class} src="{url}" alt="User avatar"'
        ' height="{size}" width="{size}">'.format(**kwargs)
    )
