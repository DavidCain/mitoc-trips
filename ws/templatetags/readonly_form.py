from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/readonly_form.html')
def readonly_form(form):
    return {'form': form}
