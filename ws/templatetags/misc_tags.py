from django import template
from django.utils.safestring import mark_safe

import phonenumbers


register = template.Library()


@register.filter
def format_phone_number(number):
    """ Format phone numbers with spacing & area code. """
    if not number:
        return ''

    # Only include country code if outside the US
    if number.country_code == 1:
        fmt = phonenumbers.PhoneNumberFormat.NATIONAL
    else:
        fmt = phonenumbers.PhoneNumberFormat.INTERNATIONAL

    return phonenumbers.format_number(number, fmt)


@register.filter
def redact(content, should_redact):
    """ Optionally replace content that should be redacted. """
    return mark_safe("<em>redacted</em>") if should_redact else content
