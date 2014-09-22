from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/messages_ul.html', takes_context=True)
def messages_ul(context):
    return {'messages': context['messages']}
