from django.db.models.fields import TextField
from django import template
register = template.Library()


@register.inclusion_tag('for_templatetags/application_details.html')
def application_details(application):
    text_fields = [
        (field, getattr(application, field.name))
        for field in application._meta.fields
        if isinstance(field, TextField)
    ]
    return {'text_fields': text_fields}
