from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf.urls.static import static
from django.views.generic import TemplateView

from ws import views
from ws import settings
from ws.decorators import group_required

# Access is controlled in views, but URLs are roughly grouped by access
urlpatterns = patterns('',
    url(r'^$', views.home, name='home'),
    # Redirect to home page after changing password (default is annoying loop)
    url(r'^accounts/password/change/$', views.login_after_password_change, name='account_change_password'),
    url(r'^accounts/', include('allauth.urls')),

    # Administrator views
    url(r'^admin/', include(admin.site.urls)),
    url(r'^admin/trips/$', views.admin_manage_trips, name='admin_manage_trips'),

    # Activity Chair views
    url(r'^chair/leaders/add/$', views.add_leader, name='add_leader'),
    url(r'^chair/participants/$', views.manage_participants, name='manage_participants'),
    url(r'^chair/applications/$', views.AllLeaderApplicationsView.as_view(), name='manage_applications'),
    url(r'^chair/applications/(?P<pk>\d+)/$', views.LeaderApplicationView.as_view(), name='view_application'),
    url(r'^chair/trips/$', views.manage_trips, name='manage_trips'),
    url(r'^chair/participants/lecture_attendance/$', views.LectureAttendanceView.as_view(), name='lecture_attendance'),

    # Activity Chairs or WIMP views
    url(r'^trips/medical/$', views.WIMPView.as_view(), name='wimp'),

    # Leader views
    url(r'^trips/create/$', views.AddTripView.as_view(), name='add_trip'),
    url(r'^trips/(?P<pk>\d+)/edit/$', views.EditTripView.as_view(), name='edit_trip'),
    url(r'^leaders/$', views.LeaderView.as_view(), name='leaders'),
    url(r'^trips/leading/$', views.LeaderTripsView.as_view(), name='view_leader_trips'),
    url(r'^trips/(?P<pk>\d+)/admin/$', views.AdminTripView.as_view(), name='admin_trip'),
    url(r'^trips/(?P<pk>\d+)/itinerary/$', views.TripInfoView.as_view(), name='trip_itinerary'),
    url(r'^trips/(?P<pk>\d+)/review/$', views.ReviewTripView.as_view(), name='review_trip'),
    url(r'^participants/(?P<pk>\d+)/$', views.ParticipantDetailView.as_view(), name='view_participant'),
    url(r'^participants/find/$', views.ParticipantLookupView.as_view(), name='participant_lookup'),
    url(r'^trips/(?P<pk>\d+)/medical/$', views.TripMedicalView.as_view(), name='trip_medical'),

    # General views (anyone can view or only participants with info)
    url(r'^personal_info/$', views.UpdateParticipantView.as_view(), name='update_info'),
    url(r'^leaders/apply/$', views.BecomeLeaderView.as_view(), name='become_leader'),
    url(r'^trips/(?P<pk>\d+)/$', views.TripView.as_view(), name='view_trip'),
    url(r'^trips/$', views.CurrentTripsView.as_view(), name='view_trips'),
    url(r'^trips/all/$', views.AllTripsView.as_view(), name='view_all_trips'),
    url(r'^trips/mine/$', views.ParticipantTripsView.as_view(), name='view_my_trips'),
    url(r'^trips/waitlisted/$', views.WaitlistTripsView.as_view(), name='view_waitlisted_trips'),
    url(r'^trips/signup/$', views.SignUpView.as_view(), name='trip_signup'),
    url(r'^preferences/lottery/$', views.LotteryPreferencesView.as_view(), name='trip_preferences'),
    url(r'^preferences/lottery/pairing/$', views.LotteryPairView.as_view(), name='lottery_pair'),

    # Help views (most pages available to anyone, some require groups)
    url(r'^contact/$', TemplateView.as_view(template_name='contact.html'), name='contact'),
    url(r'^help/$', TemplateView.as_view(template_name='help/home.html'), name='help-home'),
    url(r'^help/about/$', TemplateView.as_view(template_name='help/about.html'), name='help-about'),
    url(r'^help/participants/personal_info/$', TemplateView.as_view(template_name='help/participants/personal_info.html'), name='help-personal_info'),
    url(r'^help/participants/lottery/$', TemplateView.as_view(template_name='help/participants/lottery.html'), name='help-lottery'),
    url(r'^help/participants/signups/$', TemplateView.as_view(template_name='help/participants/signups.html'), name='help-signups'),
    url(r'^help/participants/leading_trips/$', TemplateView.as_view(template_name='help/participants/leading_trips.html'), name='help-leading_trips'),
    url(r'^help/leaders/feedback/$', group_required('leaders', 'WSC')(TemplateView.as_view(template_name='help/leaders/feedback.html')), name='help-feedback'),
    url(r'^help/leaders/trip_admin/$', group_required('leaders', 'WSC')(TemplateView.as_view(template_name='help/leaders/trip_admin.html')), name='help-trip_admin'),
    url(r'^help/wsc/wsc/$', group_required('WSC')(TemplateView.as_view(template_name='help/wsc/wsc.html')), name='help-wsc'),

    # API (must have account in system)
    url(r'^trips/(?P<pk>\d+)/overflow.json$', views.CheckTripOverflowView.as_view(), name='check_trip_overflow'),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
