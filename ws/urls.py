from django.conf.urls import patterns, include, url
from django.contrib import admin

from ws import views

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'ws.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),

    url(r'^admin/', include(admin.site.urls)),
    url(r'^add_participant/', views.add_participant),
)
