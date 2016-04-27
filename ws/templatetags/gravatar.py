import hashlib
import urllib

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def gravatar_url(email, size=40):
    email_hash = hashlib.md5(email.lower()).hexdigest()
    options = {'d': 'mm', 's': str(size), 'r': 'pg'}
    return "http://www.gravatar.com/avatar/{}?{}".format(email_hash, urllib.urlencode(options))


@register.filter
def gravatar(email, size=40):
    url = gravatar_url(email, size * 2)
    return mark_safe('<img class="img-rounded" src="{}"'
                     ' height="{size}" width="{size}">'.format(url, size=size))
