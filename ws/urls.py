from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf.urls.static import static
from django.views.generic import TemplateView

from ws import views
from ws import settings
from ws.decorators import group_required

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

    url(r'^admin_trip/(?P<pk>\d+)/$', views.AdminTripView.as_view(), name='admin_trip'),
    url(r'^view_trip/(?P<pk>\d+)/$', views.ViewTrip.as_view(), name='view_trip'),
    url(r'^review_trip/(?P<pk>\d+)/$', views.ReviewTripView.as_view(), name='review_trip'),
    url(r'^trip_medical/(?P<pk>\d+)/$', views.TripMedicalView.as_view(), name='trip_medical'),
    url(r'^view_trips/', views.ViewTrips.as_view(), name='view_trips'),
    url(r'^view_leader_trips/', views.ViewLeaderTrips.as_view(), name='view_leader_trips'),
    url(r'^view_my_trips/', views.ViewParticipantTrips.as_view(), name='view_my_trips'),
    url(r'^view_waitlisted_trips/', views.ViewWaitlistTrips.as_view(), name='view_waitlisted_trips'),

    url(r'^trip_signup/$', views.SignUpView.as_view(), name='trip_signup'),
    url(r'^trip_preferences/$', views.TripPreferencesView.as_view(), name='trip_preferences'),

    url(r'^help/$', TemplateView.as_view(template_name='help/home.html'), name='help-home'),
    url(r'^help/participants/personal_info$', TemplateView.as_view(template_name='help/participants/personal_info.html'), name='help-personal_info'),
    url(r'^help/participants/lottery$', TemplateView.as_view(template_name='help/participants/lottery.html'), name='help-lottery'),
    url(r'^help/participants/signups$', TemplateView.as_view(template_name='help/participants/signups.html'), name='help-signups'),
    url(r'^help/leaders/feedback$', group_required('leaders', 'WSC')(TemplateView.as_view(template_name='help/leaders/feedback.html')), name='help-feedback'),


) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
