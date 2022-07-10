import json

from django.forms import widgets as dj_widgets
from django.forms.utils import flatatt
from django.utils.html import format_html


class MarkdownTextarea(dj_widgets.Textarea):
    """Supply a textbox with some example Markdown in it.

    The box will be at least as large as is necessary to display the Markdown.
    """

    def __init__(self, example_text=None):
        attrs = {'rows': 4}
        if example_text:
            attrs.update(
                {
                    'rows': max(4, example_text.count('\n') + 1),
                    'placeholder': example_text,
                }
            )

        super().__init__(attrs)


class LeaderSelect(dj_widgets.SelectMultiple):
    def render(self, name, value, attrs=None, renderer=None):
        attrs.update(program='program', name=name)
        if value:
            attrs['leader-ids'] = json.dumps(value)
        final_attrs = flatatt(self.build_attrs(self.attrs, attrs))
        return format_html('<leader-select {}></leader-select>', final_attrs)


class ParticipantSelect(dj_widgets.Select):
    def render(self, name, value, attrs=None, renderer=None):
        attrs.update(name=name)
        final_attrs = self.build_attrs(self.attrs, attrs)
        return format_html(
            '<participant-select {}></participant-select>', flatatt(final_attrs)
        )


class PhoneInput(dj_widgets.Input):
    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        attrs.update(
            {
                'default-country': 'us',
                'preferred-countries': 'us ca',
                'name': name,
            }
        )
        final_attrs = self.build_attrs(self.attrs, attrs)

        # Use a hack to init ng-model. We take the provided value & populate a hidden input.
        # When the `bc-phone-number` input updates, we update the hidden input's value.
        # TODO: We should provide a plain E.164 <input type="tel"/> for `<noscript/>`
        ng_model = name.replace('-', '_')
        final_attrs['ng-model'] = ng_model

        ng_model_init = {
            'data-ng-model': ng_model,
            'data-ng-init': f"{ng_model} = '{value or str()}'",
            'value': str(value) if value else '',
        }

        return format_html(
            '<input type="hidden" {}/>' + '<bc-phone-number {}></bc-phone-number>',
            flatatt(ng_model_init),
            flatatt(final_attrs),
        )


class DateTimeLocalInput(dj_widgets.DateTimeInput):
    """Custom widget to use the `datetime-local` widget to render a datetime.

    Despite what the input type might imply, this is *not* localized (has no timezone).
    Datetimes are assumed to mean Eastern Time.

    This is expected to round to the minute, not the second!
    """

    def __init__(self, attrs=None, format=None):  # pylint:disable=redefined-builtin
        attrs = attrs or {}
        super().__init__(
            attrs={
                'type': 'datetime-local',
                # It's important to specify step size
                # Without this, we can only change the time in increments of whole minutes.
                # (In other words, a trip created to open at 09:05:55, couldn't change to 09:06:00)
                # We generally round to the whole minute *anyway*, but this is doubly important if:
                # - the value being edited was rounded to the second
                # - we only display to the minute
                'step': 'any',
                **attrs,
            },
            # Important: Firefox will work with `format=None`, where time is 'YYYY-MM-DD HH:MM'
            # *However* Chrome requires the ISO-8601 spec and fails without the crucial `T` separator
            format=format or '%Y-%m-%dT%H:%M',
        )
