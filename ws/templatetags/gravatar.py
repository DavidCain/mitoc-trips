import hashlib
import urllib

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def gravatar_url(email, size=40):
    email_hash = hashlib.md5(email.lower()).hexdigest()
    options = {'d': 'mm', 's': str(size), 'r': 'pg'}
    return "https://www.gravatar.com/avatar/{}?{}".format(email_hash, urllib.urlencode(options))


@register.filter
def gravatar_square(email, size=30):
    return gravatar(email, size, False)

@register.filter
def gravatar(email, size=40, img_rounded=True):
    kwargs = {'url': gravatar_url(email, size * 2),
              'size': size,
              'class': 'class="img-rounded"' if img_rounded else ''}
    return mark_safe('<img {class} src="{url}"'
                     ' height="{size}" width="{size}">'.format(**kwargs))
