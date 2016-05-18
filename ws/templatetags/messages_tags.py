from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/messages_alerts.html', takes_context=True)
def messages_alerts(context):
    return {'messages': context['messages']}
