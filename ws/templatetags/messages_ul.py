from django import template

register = template.Library()


def messages_ul(context):
    return {'messages': context['messages']}

# Register the custom tag as an inclusion tag with takes_context=True.
register.inclusion_tag('messages_ul.html', takes_context=True)(messages_ul)
