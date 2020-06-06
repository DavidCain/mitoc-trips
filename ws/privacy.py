import types
from collections import OrderedDict, defaultdict

from django.db.models import Q
from django.forms.models import model_to_dict

from ws import enums, models


class DataDump:
    def __init__(self, participant_id):
        all_participants = models.Participant.objects.select_related(
            'emergency_info__emergency_contact', 'car', 'lotteryinfo'
        ).prefetch_related('signup_set__trip')
        self.par = all_participants.get(pk=participant_id)

    @property
    def all_data(self):
        """ Return all data in an ordered dictionary for presentation.

        This dictionary should be able to be serialized to JSON by Django
        (though not necessarily a raw `json.dumps()`)
        """
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

    @property
    def medical(self):
        """ Represent emergency info & contact in one dictionary. """
        einfo = self.par.emergency_info
        econtact = einfo.emergency_contact
        einfo = model_to_dict(einfo, exclude=['id', 'emergency_contact_id'])
        econtact = model_to_dict(econtact, exclude=['id'])
        econtact['cell_phone'] = str(econtact['cell_phone'])
        return {**einfo, 'emergency_contact': econtact}

    @property
    def car(self):
        """ Participant's car information. """
        return self.par.car and model_to_dict(self.par.car, exclude='id')

    @property
    def discounts(self):
        """ Discounts where the participant elected to share their info. """
        for d in self.par.discounts.all():
            yield model_to_dict(d, fields=['name', 'active', 'summary', 'url'])

    @property
    def authored_feedback(self):
        """ Feedback supplied by the participant. """
        about_participant = Q(leader=self.par)
        all_feedback = models.Feedback.everything.filter(about_participant)

        for f in all_feedback.select_related('trip', 'participant'):
            trip = None if f.trip is None else {'id': f.trip.pk, 'name': f.trip.name}
            yield {
                'participant': {'id': f.participant.pk, 'name': f.participant.name},
                'comments': f.comments,
                'showed_up': f.showed_up,
                'time_created': f.time_created,
                'trip': trip,
            }

    @property
    def received_feedback(self):
        """ Feedback _about_ the participant. """
        about_participant = Q(participant=self.par)
        all_feedback = models.Feedback.everything.filter(about_participant)

        for f in all_feedback.select_related('trip', 'leader'):
            trip = None if f.trip is None else {'id': f.trip.pk, 'name': f.trip.name}
            yield {'leader': {'id': f.leader.pk, 'name': f.leader.name}, 'trip': trip}

    @property
    def feedback(self):
        return {
            'received': list(self.received_feedback),
            'given': list(self.authored_feedback),
        }

    @property
    def winter_school_lecture_attendance(self):
        """ Attendance to Winter School lectures. """
        for attendance in self.par.lectureattendance_set.all():
            yield {
                'year': attendance.year,
                'time_created': attendance.time_created,  # model_to_dict omits!
            }

    @property
    def signups(self):
        """ All signups, whether on the trip or not. """
        signups = self.par.signup_set
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
            info = self.par.lotteryinfo
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
            'wimped': repr_trips(self.par.wimp_trips),
            'led': repr_trips(self.par.trips_led.all()),
            'created': repr_trips(self.par.created_trips.all()),
        }

    @property
    def membership(self):
        """ Cached membership information. """
        mem = self.par.membership
        if not mem:
            return None

        return model_to_dict(mem, fields=['membership_expires', 'waiver_expires'])

    @property
    def user(self):
        """ Combine User and Participant record into one representation. """
        user = self.par.user
        return {
            **model_to_dict(user, fields=['last_login', 'date_joined']),
            'name': self.par.name,
            'profile_last_updated': self.par.profile_last_updated,
            'cell_phone': self.par.cell_phone and str(self.par.cell_phone),
            'affiliation': self.par.get_affiliation_display(),
            'emails': [
                model_to_dict(e, fields=['email', 'verified', 'primary'])
                for e in user.emailaddress_set.all()
            ],
        }

    @property
    def _ws_applications(self):
        """ All Winter School leader applications by the user. """
        ws_apps = models.WinterSchoolLeaderApplication.objects.filter(
            participant=self.par
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
        return dict(self._applications_by_activity)

    @property
    def _applications_by_activity(self):
        ws_apps = list(self._ws_applications)
        if ws_apps:
            yield enums.Activity.WINTER_SCHOOL.label, ws_apps

        by_participant = Q(participant=self.par)

        normal_apps = [
            (enums.Activity.HIKING.label, models.HikingLeaderApplication),
            (enums.Activity.CLIMBING.label, models.ClimbingLeaderApplication),
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
        for rating in self.par.leaderrating_set.select_related('creator').all():
            formatted = model_to_dict(rating, fields=['rating', 'notes', 'active'])
            formatted.update(
                creator={'id': rating.creator.id, 'name': rating.creator.name},
                time_created=rating.time_created,
            )
            by_activity[rating.activity].append(formatted)
        return dict(by_activity)
