from django.db.models.fields import TextField
from django import template

from ws import models

register = template.Library()


@register.inclusion_tag('for_templatetags/application_summary.html')
def application_summary(application):
    previous_ratings = models.LeaderRating.objects.filter(
        participant=application.participant,
        activity=application.activity,
        time_created__lte=application.time_created
    ).order_by('-active', '-time_created')

    return {'application': application, 'previous_ratings': previous_ratings}

@register.inclusion_tag('for_templatetags/application_details.html')
def application_details(application):
    all_fields = application._meta.fields
    text_fields = [
        (field, getattr(application, field.name))
        for field in all_fields if isinstance(field, TextField)
    ]

    familiarities = []
    lead = 'familiarity_'
    for field in (f for f in all_fields if f.name.startswith(lead)):
        if field.name == 'familiarity_sr':
            short_label = 'self-rescue'
        else:
            short_label = field.name[len(lead):].replace('_', ' ')
        response = getattr(application, 'get_' + field.name + '_display')()
        familiarities.append((short_label, response))

    return {'familiarities': familiarities, 'text_fields': text_fields}


@register.inclusion_tag('for_templatetags/application_description.html')
def application_description(activity):
    return {'activity': activity}


@register.inclusion_tag('for_templatetags/application_status.html')
def application_status(latest_application, can_apply):
    return {'rating_given': latest_application.rating_given,
            'activity': latest_application.activity,
            'can_apply': can_apply}


@register.inclusion_tag('for_templatetags/ws_application.html')
def ws_application(form):
    return {'form': form}
