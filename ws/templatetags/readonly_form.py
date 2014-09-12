from django import template

register = template.Library()


def readonly_form(form):
    return {'form': form}

# Register the custom tag as an inclusion tag with takes_context=True.
register.inclusion_tag('readonly_form.html')(readonly_form)
