from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf.urls.static import static

from ws import views
from ws import settings

urlpatterns = patterns('',
    url(r'^accounts/$', views.account_home),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^accounts/update_info/', views.update_info),
    url(r'^accounts/wsc/add_leader/', views.add_leader),
    url(r'^accounts/wsc/manage_leaders/', views.manage_leaders),

) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
