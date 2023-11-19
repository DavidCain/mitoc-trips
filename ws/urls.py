from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView, TemplateView

from ws import api_views, feeds, settings, views
from ws.decorators import group_required

# Access is controlled in views, but URLs are roughly grouped by access
urlpatterns = [
    path("", views.ProfileView.as_view(), name="home"),
    path(
        "profile/",
        RedirectView.as_view(url=reverse_lazy("home"), permanent=True),
        name="profile",
    ),
    # Redirect to home page after changing password (default is annoying loop)
    path(
        "accounts/password/change/",
        views.CustomPasswordChangeView.as_view(),
        name="account_change_password",
    ),
    path(
        "accounts/login/",
        views.CheckIfPwnedOnLoginView.as_view(),
        name="account_login",
    ),
    path("accounts/", include("allauth.urls")),
    # Administrator views
    path("admin", admin.site.urls),
    path(
        "participants/<int:pk>/edit/",
        views.EditParticipantView.as_view(),
        name="edit_participant",
    ),
    path(
        "participants/<int:pk>/delete/",
        views.DeleteParticipantView.as_view(),
        name="delete_participant",
    ),
    path(
        "participants/potential_duplicates/",
        views.PotentialDuplicatesView.as_view(),
        name="potential_duplicates",
    ),
    path(
        "participants/<int:old>/merge/<int:new>",
        views.MergeParticipantsView.as_view(),
        name="merge_participants",
    ),
    path(
        "participants/<int:left>/distinct/<int:right>",
        views.DistinctParticipantsView.as_view(),
        name="distinct_participants",
    ),
    path(
        "<slug:activity>/leaders/",
        views.ActivityLeadersView.as_view(),
        name="activity_leaders",
    ),
    path(
        "<slug:activity>/leaders/deactivate/",
        views.DeactivateLeaderRatingsView.as_view(),
        name="deactivate_leaders",
    ),
    path(
        "<slug:activity>/applications/",
        views.AllLeaderApplicationsView.as_view(),
        name="manage_applications",
    ),
    path(
        "<slug:activity>/applications/<int:pk>/",
        views.LeaderApplicationView.as_view(),
        name="view_application",
    ),
    path(
        "<slug:activity>/applications/<int:pk>/archive/",
        views.ArchiveLeaderApplicationView.as_view(),
        name="archive_application",
    ),
    path(
        "<slug:activity>/trips/",
        views.ApproveTripsView.as_view(),
        name="manage_trips",
    ),
    path(
        "winter_school/settings/",
        views.WinterSchoolSettingsView.as_view(),
        name="ws_settings",
    ),
    path(
        "<slug:activity>/trips/<int:pk>/",
        views.ChairTripView.as_view(),
        name="view_trip_for_approval",
    ),
    path(
        "trips/<int:pk>/approve/",
        api_views.ApproveTripView.as_view(),
        name="json-approve_trip",
    ),
    # Activity Chairs or WIMP views
    path(
        "trips/medical/",
        views.AllTripsMedicalView.as_view(),
        name="all_trips_medical",
    ),
    path(
        "trips/search/",
        views.TripSearchView.as_view(),
        name="search_trips",
    ),
    # Leader views
    path("leaders/", views.AllLeadersView.as_view(), name="leaders"),
    path("trips/create/", views.CreateTripView.as_view(), name="create_trip"),
    path(
        "trips/<int:pk>/delete/",
        views.DeleteTripView.as_view(),
        name="delete_trip",
    ),
    path("trips/<int:pk>/edit/", views.EditTripView.as_view(), name="edit_trip"),
    path(
        "trips/<int:pk>/admin/",
        RedirectView.as_view(pattern_name="view_trip", permanent=True),
        name="admin_trip",
    ),
    path(
        "trips/<int:pk>/admin/signups/",
        api_views.AdminTripSignupsView.as_view(),
        name="json-admin_trip_signups",
    ),
    path(
        "trips/<int:pk>/admin/lottery/",
        views.RunTripLotteryView.as_view(),
        name="run_lottery",
    ),
    path(
        "trips/<int:pk>/signup/",
        api_views.LeaderParticipantSignupView.as_view(),
        name="json-leader_participant_signup",
    ),
    path(
        "trips/<int:pk>/itinerary/",
        views.TripItineraryView.as_view(),
        name="trip_itinerary",
    ),
    path(
        "trips/<int:pk>/medical/",
        views.TripMedicalView.as_view(),
        name="trip_medical",
    ),
    path(
        "trips/<int:pk>/review/",
        views.ReviewTripView.as_view(),
        name="review_trip",
    ),
    path(
        "participants/<int:pk>/",
        views.ParticipantDetailView.as_view(),
        name="view_participant",
    ),
    path(
        "participants/<int:pk>/membership/",
        views.RefreshMembershipView.as_view(),
        name="refresh_participant_membership",
    ),
    path(
        "participants/",
        views.ParticipantLookupView.as_view(),
        name="participant_lookup",
    ),
    path(
        "participants/membership_statuses/",
        api_views.MembershipStatusesView.as_view(),
        name="json-membership_statuses",
    ),
    # General views (anyone can view or only participants with info)
    path("profile/edit/", views.EditProfileView.as_view(), name="edit_profile"),
    path(
        "leaders/apply/",
        views.AnyActivityLeaderApplyView.as_view(),
        name="leaders_apply",
    ),
    path("profile/membership/", views.PayDuesView.as_view(), name="pay_dues"),
    path("profile/waiver/", views.SignWaiverView.as_view(), name="initiate_waiver"),
    path(
        "<slug:activity>/leaders/apply/",
        views.LeaderApplyView.as_view(),
        name="become_leader",
    ),
    path("trips/<int:pk>/", views.TripView.as_view(), name="view_trip"),
    path("trips.rss", feeds.UpcomingTripsFeed(), name="rss-upcoming_trips"),
    # By default, `/trips/` shows only upcoming trips
    # Both views support filtering for trips after a certain date, though
    path("trips/", views.UpcomingTripsView.as_view(), name="upcoming_trips"),
    # With thousands of trips, we can no longer render them all on one page.
    path(
        "trips/all/",
        RedirectView.as_view(url=reverse_lazy("upcoming_trips"), permanent=True),
        name="all_trips",
    ),
    path("trips/signup/", views.SignUpView.as_view(), name="trip_signup"),
    path(
        "trips/signup/leader/",
        views.LeaderSignUpView.as_view(),
        name="leader_trip_signup",
    ),
    path("preferences/discounts/", views.DiscountsView.as_view(), name="discounts"),
    path(
        "preferences/email/",
        views.EmailPreferencesView.as_view(),
        name="email_preferences",
    ),
    path(
        "preferences/email/unsubscribe/<str:token>/",
        views.EmailUnsubscribeView.as_view(),
        name="email_unsubscribe",
    ),
    path(
        "preferences/lottery/",
        views.LotteryPreferencesView.as_view(),
        name="lottery_preferences",
    ),
    path(
        "preferences/lottery/pairing/",
        views.LotteryPairingView.as_view(),
        name="lottery_pairing",
    ),
    path(
        "signups/<int:pk>/delete/",
        views.DeleteSignupView.as_view(),
        name="delete_signup",
    ),
    path(
        "winter_school/participants/lecture_attendance/",
        views.LectureAttendanceView.as_view(),
        name="lecture_attendance",
    ),
    # Help views (most pages available to anyone, some require groups)
    path(
        "contact/",
        TemplateView.as_view(template_name="contact.html"),
        name="contact",
    ),
    path(
        "help/",
        TemplateView.as_view(template_name="help/home.html"),
        name="help-home",
    ),
    path(
        "help/about/",
        TemplateView.as_view(template_name="help/about.html"),
        name="help-about",
    ),
    # Privacy views
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
    path(
        "privacy/download/",
        views.PrivacyDownloadView.as_view(),
        name="privacy_download",
    ),
    path(
        "privacy/download.json",
        views.JsonDataDumpView.as_view(),
        name="json-data_dump",
    ),
    path(
        "privacy/settings/",
        views.PrivacySettingsView.as_view(),
        name="privacy_settings",
    ),
    path(
        "help/participants/wimp/",
        TemplateView.as_view(template_name="help/participants/wimp_guide.html"),
        name="help-wimp_guide",
    ),
    # Participating on Trips
    path(
        "help/participants/personal_info/",
        TemplateView.as_view(template_name="help/participants/personal_info.html"),
        name="help-personal_info",
    ),
    path(
        "help/participants/lottery/",
        TemplateView.as_view(template_name="help/participants/lottery.html"),
        name="help-lottery",
    ),
    path(
        "help/participants/signups/",
        TemplateView.as_view(template_name="help/participants/signups.html"),
        name="help-signups",
    ),
    # Leading Trips
    path(
        "help/participants/become_ws_leader/",
        TemplateView.as_view(template_name="help/participants/become_ws_leader.html"),
        name="help-become_ws_leader",
    ),
    path(
        "help/participants/trip_difficulty/",
        TemplateView.as_view(template_name="help/participants/trip_difficulty.html"),
        name="help-trip_difficulty",
    ),
    path(
        "help/participants/ws_ratings/",
        TemplateView.as_view(template_name="help/participants/ws_ratings.html"),
        name="help-ws_ratings",
    ),
    path(
        "help/participants/ws_rating_assignment/",
        TemplateView.as_view(
            template_name="help/participants/ws_rating_assignment.html"
        ),
        name="help-ws_rating_assignment",
    ),
    # Planning Trips
    path(
        "help/participants/rentals/",
        TemplateView.as_view(template_name="help/leaders/rentals.html"),
        name="help-rentals",
    ),
    path(
        "help/participants/weather/",
        TemplateView.as_view(template_name="help/participants/weather.html"),
        name="help-weather",
    ),
    path(
        "help/participants/maps/",
        TemplateView.as_view(template_name="help/participants/maps.html"),
        name="help-maps",
    ),
    # Trip Logistics (for leaders)
    path(
        "help/leaders/trip_admin/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/trip_admin.html")
        ),
        name="help-trip_admin",
    ),
    path(
        "help/leaders/checklist/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/checklist.html")
        ),
        name="help-checklist",
    ),
    path(
        "help/leaders/example_emails/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/example_emails.html")
        ),
        name="help-example_emails",
    ),
    path(
        "help/leaders/rideshare/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/rideshare.html")
        ),
        name="help-rideshare",
    ),
    path(
        "help/leaders/itinerary/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/itinerary.html")
        ),
        name="help-itinerary",
    ),
    path(
        "help/leaders/ws_gear/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/ws_gear.html")
        ),
        name="help-ws_gear",
    ),
    path(
        "help/leaders/feedback/",
        group_required({"leaders", "WSC"})(
            TemplateView.as_view(template_name="help/leaders/feedback.html")
        ),
        name="help-feedback",
    ),
    # WSC Administration (for the Winter Safety Committee)
    path(
        "help/wsc/wsc/",
        group_required("WSC")(TemplateView.as_view(template_name="help/wsc/wsc.html")),
        name="help-wsc",
    ),
    # API
    path(
        "programs/<slug:program>/leaders.json",
        api_views.JsonProgramLeadersView.as_view(),
        name="json-program-leaders",
    ),
    path(
        "participants.json",
        api_views.JsonParticipantsView.as_view(),
        name="json-participants",
    ),
    path(
        "leaders/<int:pk>/ratings/<slug:activity>.json",
        api_views.get_rating,
        name="json-ratings",
    ),
    path(
        "users/<int:pk>/membership.json",
        api_views.UserMembershipView.as_view(),
        name="json-membership",
    ),
    path(
        "users/<int:pk>/rentals.json",
        api_views.UserRentalsView.as_view(),
        name="json-rentals",
    ),
    path(
        "trips/<int:pk>/signups/",
        api_views.SimpleSignupsView.as_view(),
        name="json-signups",
    ),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("stats/leaderboard/", views.LeaderboardView.as_view(), name="leaderboard"),
    path(
        "stats/membership/",
        views.MembershipStatsView.as_view(),
        name="membership_stats",
    ),
    path(
        "stats/membership.json",
        api_views.RawMembershipStatsView.as_view(),
        name="json-membership_stats",
    ),
    # JSON-returning routes that depend on HTTP authorization
    # Tokens accepted via Authorization header (standard 'Bearer' format)
    path(
        "data/verified_emails/",
        api_views.OtherVerifiedEmailsView.as_view(),
        name="other_verified_emails",
    ),
    path(
        "data/membership/",
        api_views.UpdateMembershipView.as_view(),
        name="update_membership",
    ),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

try:
    import debug_toolbar
except ImportError:
    pass
else:
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls)), *urlpatterns]
