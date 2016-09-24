from django import template
from copy import copy

register = template.Library()


@register.inclusion_tag('for_templatetags/form_group.html')
def form_group(field, use_help_icon=False):
    return {'field': field, 'use_help_icon': use_help_icon}


@register.inclusion_tag('for_templatetags/readonly_form.html')
def readonly_form(form):
    return {'form': form}


@register.filter
def instances_and_widgets(bound_field):
    """Returns a list of two-tuples of instances and widgets, designed to
    be used with ModelMultipleChoiceField and CheckboxSelectMultiple widgets.

    Allows templates to loop over a multiple checkbox field and display the
    related model instance, such as for a table with checkboxes.

    Usage:
       {% for instance, widget in form.my_field_name|instances_and_widgets %}
           <p>{{ instance }}: {{ widget }}</p>
       {% endfor %}
    """
    # Source: http://stackoverflow.com/a/27545910/815632
    for i, instance in enumerate(bound_field.field.queryset.all()):
        yield (instance, copy(bound_field[i]))
