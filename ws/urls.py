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
    url(r'^update_info/', views.UpdateParticipantView.as_view(), name='update_info'),
    url(r'^wsc/add_leader/', views.add_leader, name='add_leader'),
    url(r'^wsc/manage_leaders/', views.manage_leaders, name='manage_leaders'),
    url(r'^wsc/manage_participants/', views.manage_participants, name='manage_participants'),
    url(r'^wsc/manage_trips/', views.manage_trips, name='manage_trips'),
    url(r'^view_participant/(?P<pk>\d+)/$', views.ParticipantDetailView.as_view(), name='view_participant'),
    url(r'^view_trip/(?P<pk>\d+)/$', views.ViewTrip.as_view(), name='view_trip'),
    url(r'^view_trips/', views.ViewTrips.as_view(), name='view_trips'),
    url(r'^trip_signup/$', views.SignUpView.as_view(), name='trip_signup'),
    url(r'^trip_preferences/$', views.trip_preferences, name='trip_preferences'),

) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
