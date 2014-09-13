from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf.urls.static import static

from ws import views
from ws import settings

urlpatterns = patterns('',
    url(r'^$', views.home, name="home"),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^add_trip/', views.AddTrip.as_view(), name='add_trip'),
    url(r'^accounts/update_info/', views.UpdateParticipantView.as_view(), name='update_info'),
    url(r'^accounts/wsc/add_leader/', views.add_leader, name='add_leader'),
    url(r'^accounts/wsc/manage_leaders/', views.manage_leaders, name='manage_leaders'),
    url(r'^accounts/wsc/manage_participants/', views.manage_participants, name='manage_participants'),
    url(r'^accounts/wsc/manage_trips/', views.manage_trips, name='manage_trips'),
    url(r'^accounts/view_participant/(?P<pk>\d+)/$', views.ParticipantDetailView.as_view(), name='view_participant'),
    url(r'^accounts/view_trip/(?P<pk>\d+)/$', views.TripDetailView.as_view(), name='view_trip'),

) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
