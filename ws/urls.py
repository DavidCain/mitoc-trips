from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf.urls.static import static
from django.core.urlresolvers import reverse_lazy
from django.views.generic import RedirectView, TemplateView

from ws import views
from ws import settings
from ws.decorators import group_required

# Access is controlled in views, but URLs are roughly grouped by access
urlpatterns = patterns('',
    url(r'^$', views.ProfileView.as_view(), name='home'),
    url(r'^profile/*$', RedirectView.as_view(url=reverse_lazy('home'), permanent=True), name='profile'),

    # Redirect to home page after changing password (default is annoying loop)
    url(r'^accounts/password/change/$', views.login_after_password_change, name='account_change_password'),
    url(r'^accounts/', include('allauth.urls')),

    # Administrator views
    url(r'^admin/', include(admin.site.urls)),
    url(r'^admin/trips/$', views.admin_manage_trips, name='admin_manage_trips'),
    url(r'^participants/(?P<pk>\d+)/edit/$', views.EditParticipantView.as_view(), name='edit_participant'),
    url(r'^participants/(?P<pk>\d+)/delete/$', views.DeleteParticipantView.as_view(), name='delete_participant'),

    # Activity Chair views
    url(r'^chair/leaders/$', views.manage_leaders, name='manage_leaders'),
    url(r'^chair/applications/$', views.AllLeaderApplicationsView.as_view(), name='manage_applications'),
    url(r'^chair/applications/(?P<pk>\d+)/$', views.LeaderApplicationView.as_view(), name='view_application'),
    url(r'^chair/trips/$', views.manage_trips, name='manage_trips'),
    url(r'^chair/participants/lecture_attendance/$', views.LectureAttendanceView.as_view(), name='lecture_attendance'),

    # Activity Chairs or WIMP views
    url(r'^trips/medical/$', views.AllTripsMedicalView.as_view(), name='all_trips_medical'),

    # Leader views
    url(r'^leaders/$', views.AllLeadersView.as_view(), name='leaders'),
    url(r'^trips/create/$', views.CreateTripView.as_view(), name='create_trip'),
    url(r'^trips/(?P<pk>\d+)/delete/$', views.DeleteTripView.as_view(), name='delete_trip'),
    url(r'^trips/(?P<pk>\d+)/edit/$', views.EditTripView.as_view(), name='edit_trip'),
    url(r'^trips/(?P<pk>\d+)/admin/$', views.AdminTripView.as_view(), name='admin_trip'),
    url(r'^trips/(?P<pk>\d+)/admin/signups/$', views.AdminTripSignupsView.as_view(), name='admin_trip_signups'),
    url(r'^trips/(?P<pk>\d+)/itinerary/$', views.TripItineraryView.as_view(), name='trip_itinerary'),
    url(r'^trips/(?P<pk>\d+)/medical/$', views.TripMedicalView.as_view(), name='trip_medical'),
    url(r'^trips/(?P<pk>\d+)/review/$', views.ReviewTripView.as_view(), name='review_trip'),
    url(r'^participants/(?P<pk>\d+)/$', views.ParticipantDetailView.as_view(), name='view_participant'),
    url(r'^participants/find/$', views.ParticipantLookupView.as_view(), name='participant_lookup'),

    # General views (anyone can view or only participants with info)
    url(r'^profile/edit/$', views.EditProfileView.as_view(), name='edit_profile'),
    url(r'^leaders/apply/$', views.LeaderApplyView.as_view(), name='become_leader'),
    url(r'^trips/(?P<pk>\d+)/$', views.TripView.as_view(), name='view_trip'),
    url(r'^trips/$', views.UpcomingTripsView.as_view(), name='upcoming_trips'),
    url(r'^trips/all/$', views.AllTripsView.as_view(), name='all_trips'),
    url(r'^trips/signup/$', views.SignUpView.as_view(), name='trip_signup'),
    url(r'^trips/signup/leader$', views.LeaderSignUpView.as_view(), name='leader_trip_signup'),
    url(r'^preferences/lottery/$', views.LotteryPreferencesView.as_view(), name='lottery_preferences'),
    url(r'^preferences/lottery/pairing/$', views.LotteryPairingView.as_view(), name='lottery_pairing'),

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
    url(r'^leaders.json/(?:(?P<activity>.+)/)?$', views.JsonAllLeadersView.as_view(), name='json-leaders'),
    url(r'^leaders/(?P<pk>\d+)/ratings/(?P<activity>.+).json', views.get_rating, name='get_rating'),
    url(r'^users/(?P<user_id>\d+)/membership.json', views.membership_status, name='membership_status'),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
