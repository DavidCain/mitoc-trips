import json

from django import template

from ws import settings

register = template.Library()


@register.inclusion_tag('for_templatetags/raven_user_context.html', takes_context=True)
def raven_user_context(context, user, participant):
    """ Include JavaScript that should only be present in production. """
    user_context = {}
    if user and user.is_authenticated:
        user_context['email'] = user.email
        if participant:
            user_context['participant_id'] = participant.pk
            user_context['name'] = participant.name

    return {'DEBUG': settings.DEBUG, 'user_context': json.dumps(user_context)}
