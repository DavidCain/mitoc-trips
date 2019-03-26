from collections import defaultdict, OrderedDict
import types


from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
from django.forms.models import model_to_dict
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView
from django.views.generic.detail import SingleObjectMixin

from ws.decorators import participant_required
from ws import forms
from ws import models


class NeedsParticipant:
    @method_decorator(participant_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PrivacySettingsView(NeedsParticipant, FormView):
    template_name = 'privacy/settings.html'
    success_url = reverse_lazy('privacy_settings')
    form_class = forms.PrivacySettingsForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.request.participant
        return kwargs

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class PrivacyView(TemplateView):
    template_name = 'privacy/home.html'


class PrivacyDownloadView(TemplateView):
    template_name = 'privacy/download.html'


class JsonDataDumpView(NeedsParticipant, TemplateView, SingleObjectMixin):
    def get_object(self, queryset=None):
        self.kwargs['pk'] = self.request.participant.pk
        return super().get_object(queryset)

    def get_queryset(self):
        joins = ['emergency_info__emergency_contact', 'car', 'lotteryinfo']
        return models.Participant.objects.select_related(*joins).prefetch_related(
            'signup_set__trip'
        )

    @property
    def medical(self):
        """ Represent emergency info & contact in one dictionary. """
        einfo = self.object.emergency_info
        econtact = einfo.emergency_contact
        einfo = model_to_dict(einfo, exclude=['id', 'emergency_contact_id'])
        econtact = model_to_dict(econtact, exclude=['id'])
        econtact['cell_phone'] = str(econtact['cell_phone'])
        return {**einfo, 'emergency_contact': econtact}

    @property
    def car(self):
        """ Participant's car information. """
        return self.object.car and model_to_dict(self.object.car, exclude='id')

    @property
    def discounts(self):
        """ Discounts where the participant elected to share their info. """
        for d in self.object.discounts.all():
            yield model_to_dict(d, fields=['name', 'active', 'summary', 'url'])

    @property
    def authored_feedback(self):
        """ Feedback supplied by the participant. """
        about_participant = Q(leader=self.object)
        all_feedback = models.Feedback.everything.filter(about_participant)

        for f in all_feedback.select_related('trip', 'participant'):
            yield {
                'participant': {'id': f.participant.pk, 'name': f.participant.name},
                'comments': f.comments,
                'showed_up': f.showed_up,
                'time_created': f.time_created,
                'trip': {'id': f.trip.pk, 'name': f.trip.name},
            }

    @property
    def received_feedback(self):
        """ Feedback _about_ the participant. """
        about_participant = Q(participant=self.object)
        all_feedback = models.Feedback.everything.filter(about_participant)

        for f in all_feedback.select_related('trip', 'leader'):
            yield {
                'leader': {'id': f.leader.pk, 'name': f.leader.name},
                'trip': {'id': f.trip.pk, 'name': f.trip.name},
            }

    @property
    def feedback(self):
        return {
            'received': list(self.received_feedback),
            'given': list(self.authored_feedback),
        }

    @property
    def winter_school_lecture_attendance(self):
        """ Attendance to Winter School lectures. """
        for attendance in self.object.lectureattendance_set.all():
            yield {
                'year': attendance.year,
                'time_created': attendance.time_created,  # model_to_dict omits!
            }

    @property
    def signups(self):
        """ All signups, whether on the trip or not. """
        signups = self.object.signup_set
        for s in signups.all():
            yield {
                'time_created': s.time_created,
                'last_updated': s.last_updated,
                'notes': s.notes,
                'on_trip': s.on_trip,
                'trip': {'id': s.trip.pk, 'name': s.trip.name},
            }

    @property
    def lottery_info(self):
        """ Lottery information (excluding trip ranking, found in signups). """
        try:
            info = self.object.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            return None
        return {
            'car_status': info.get_car_status_display(),
            'number_of_passengers': info.number_of_passengers,
            'last_updated': info.last_updated,
            'paired_with': info.paired_with and info.paired_with.name,
        }

    @property
    def trips(self):
        """ Trips that the participant WIMPed, led, or created. """

        def repr_trips(manager):
            return [
                model_to_dict(trip, fields=['id', 'name']) for trip in manager.all()
            ]

        return {
            'wimped': repr_trips(self.object.wimp_trips),
            'led': repr_trips(self.object.trips_led.all()),
            'created': repr_trips(self.object.created_trips.all()),
        }

    @property
    def membership(self):
        """ Cached membership information. """
        try:
            mem = self.object.membership
        except models.LotteryInfo.DoesNotExist:
            return None
        fields = ['membership_expires', 'waiver_expires', 'last_cached']
        return model_to_dict(mem, fields=fields)

    @property
    def user(self):
        """ Combine User and Participant record into one representation. """
        par = self.object
        return {
            **model_to_dict(self.request.user, fields=['last_login', 'date_joined']),
            'name': par.name,
            'profile_last_updated': par.profile_last_updated,
            'cell_phone': par.cell_phone and str(par.cell_phone),
            'affiliation': par.get_affiliation_display(),
            'emails': [
                model_to_dict(e, fields=['email', 'verified', 'primary'])
                for e in self.request.user.emailaddress_set.all()
            ],
        }

    @property
    def ws_applications(self):
        """ All Winter School leader applications by the user. """
        ws_apps = models.WinterSchoolLeaderApplication.objects.filter(
            participant=self.object
        ).prefetch_related('mentor_activities', 'mentee_activities')

        for app in ws_apps.all():
            formatted = model_to_dict(app, exclude=['id', 'participant'])
            formatted.update(
                mentor_activities=[act.name for act in formatted['mentor_activities']],
                mentee_activities=[act.name for act in formatted['mentee_activities']],
            )
            yield formatted

    @property
    def leader_applications(self):
        return dict(self.applications_by_activity)

    @property
    def applications_by_activity(self):
        ws_apps = list(self.ws_applications)
        if ws_apps:
            yield models.LeaderRating.WINTER_SCHOOL, ws_apps

        by_participant = Q(participant=self.object)

        normal_apps = [
            (models.LeaderRating.HIKING, models.HikingLeaderApplication),
            (models.LeaderRating.CLIMBING, models.ClimbingLeaderApplication),
        ]
        for activity, app_model in normal_apps:
            applications = [
                model_to_dict(app, exclude=['id', 'participant'])
                for app in app_model.objects.filter(by_participant)
            ]
            if applications:
                yield activity, applications

    @property
    def leader_ratings(self):
        by_activity = defaultdict(list)
        for rating in self.object.leaderrating_set.select_related('creator').all():
            formatted = model_to_dict(rating, fields=['rating', 'notes', 'active'])
            formatted.update(
                creator={'id': rating.creator.id, 'name': rating.creator.name},
                time_created=rating.time_created,
            )
            by_activity[rating.activity].append(formatted)
        return dict(by_activity)

    @property
    def all_data(self):
        """ Return all data in an ordered dictionary for presentation. """
        self.object = self.get_object()

        fields = [
            'user',
            'membership',
            'discounts',
            'car',
            'medical',
            'lottery_info',
            'leader_ratings',
            'leader_applications',
            'winter_school_lecture_attendance',
            'trips',
            'signups',
            'feedback',
        ]
        data = OrderedDict((name, getattr(self, name)) for name in fields)

        # Coerce generators to lists for serialization as arrays
        # (simplejson has `iterable_as_array`, but this is good enough)
        for key, item in data.items():
            if isinstance(item, types.GeneratorType):
                data[key] = list(item)

        return data

    def get(self, request, *args, **kwargs):
        response = JsonResponse(self.all_data, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = 'attachment; filename=data_export.json'
        return response

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
