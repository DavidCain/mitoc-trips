from django.views.generic import TemplateView


class StatsView(TemplateView):
    template_name = 'stats/index.html'
