from django import template

register = template.Library()


@register.inclusion_tag("for_templatetags/messages_alerts.html", takes_context=True)
def messages_alerts(context):
    return {"messages": context["messages"]}


# Map the messages level to the corresponding Bootstrap alert class
bootstrap_mappings = {
    "error": "alert-danger",
    "success": "alert-success",
    "warning": "alert-warning",
    "info": "alert-info",
}


@register.filter
def alert_classes(message):
    bs_tags = ["alert"]
    if message.tags:
        bs_tags.append(bootstrap_mappings.get(message.level_tag))
    return " ".join(bs_tags)
