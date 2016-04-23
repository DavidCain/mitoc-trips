import json

from django.forms import widgets as dj_widgets
from django.utils.html import format_html
from django.forms.utils import flatatt
from django.utils.safestring import mark_safe


class BootstrapDateInput(dj_widgets.DateInput):
    """ Use the AngularUI datepicker element.

    If passing in "format," it must comply to Angular's date filter:
        https://docs.angularjs.org/api/ng/filter/date
    """
    def _set_datepicker_settings(self):
        """ Configure the datepicker with directive arguments. """
        self.attrs['data-uib-datepicker-popup'] = self.format or 'yyyy-MM-dd'
        self.attrs['show-weeks'] = False

    def render(self, name, value, attrs=None, format=None):
        """ Render normal date text input with a calendar dropdown. """
        for is_open in ['is-open', 'data-is-open']:
            if is_open in self.attrs:
                break
        else:
            self.attrs[is_open] = '{}_status.opened'.format(name)

        self._set_datepicker_settings()
        self.attrs['data-ng-init'] = "{}=false".format(self.attrs[is_open])

        date_input = super(BootstrapDateInput, self).render(name, value, attrs)
        return format_html(
            '''<span class="input-group">
                  <span class="input-group-btn">
                    <button type="button" class="btn btn-default"
                            data-ng-click="{}=true">
                      <i class="glyphicon glyphicon-calendar"></i>
                    </button>
                  </span>
                  {}
               </span>'''.format(self.attrs[is_open], date_input)
        )


class LeaderSelect(dj_widgets.SelectMultiple):
    def render(self, name, value, attrs=None, choices=()):
        self.attrs['activity'] = 'activity'
        if value:
            attrs['leader-ids'] = json.dumps(value)
        final_attrs = self.build_attrs(attrs, name=name)
        output = [format_html('<leader-select {}></leader-select>', flatatt(final_attrs))]
        return mark_safe('\n'.join(output))
