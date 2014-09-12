from django.conf.urls import patterns, include, url
from django.contrib import admin
from django.conf.urls.static import static

from ws import views
from ws import settings

urlpatterns = patterns('',
    url(r'^accounts/$', views.account_home),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^accounts/', include('allauth.urls')),
    url(r'^accounts/add_trip', views.AddTrip.as_view()),
    url(r'^accounts/update_info/', views.UpdateParticipantView.as_view()),
    url(r'^accounts/wsc/$', views.wsc_home),
    url(r'^accounts/wsc/add_leader/', views.add_leader),
    url(r'^accounts/wsc/manage_leaders/', views.manage_leaders),
    url(r'^accounts/wsc/manage_participants/', views.manage_participants),
    url(r'^accounts/view_participant/(?P<pk>\d+)/$', views.ParticipantDetailView.as_view(), name='participant-detail'),
    url(r'^accounts/view_trip/(?P<pk>\d+)/$', views.TripDetailView.as_view(), name='trip-detail'),

) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
