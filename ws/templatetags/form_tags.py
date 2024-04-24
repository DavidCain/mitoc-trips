from copy import copy

from django import template

register = template.Library()


@register.inclusion_tag("for_templatetags/readonly_form.html")
def readonly_form(form):
    return {"form": form}


@register.filter
def instances_and_widgets(bound_field):
    """Yields instances and widgets for use with ModelMultipleChoiceField & CheckboxSelectMultiple.

    Allows templates to loop over a multiple checkbox field and display the
    related model instance, such as for a table with checkboxes.

    Usage:
       {% for instance, widget in form.my_field_name|instances_and_widgets %}
           <p>{{ instance }}: {{ widget }}</p>
       {% endfor %}
    """
    # Source: https://stackoverflow.com/a/27545910/815632
    for i, instance in enumerate(bound_field.field.queryset.all()):
        yield (instance, copy(bound_field[i]))
