from datetime import timedelta

from django.db.models import Case, F, IntegerField, Q, Sum, When

from ws import models
from ws.utils.dates import ws_year, local_date, local_now
import ws.utils.perms as perm_utils


def deactivate_ratings(participant, activity):
    """ Mark any existing ratings for the activity as inactive. """
    find_ratings = {'participant__pk': participant.pk,
                    'activity': activity,
                    'active': True}
    for existing in models.LeaderRating.objects.filter(Q(**find_ratings)):
        existing.active = False
        existing.save()


class LeaderApplicationMixin(object):
    """ Some common tools for interacting with LeaderApplication objects.

    Requires self.activity
    """
    def can_reapply(self, latest_application):
        """ Winter School allows one application per year.

        Other activities just impose a reasonable waiting time.
        """
        if not latest_application:
            return True  # Not "re-applying," just applying for first time

        if latest_application.activity == models.LeaderRating.WINTER_SCHOOL:
            return latest_application.year < self.application_year

        # Allow upgrades after 2 weeks, repeat applications after ~6 months
        waiting_period_days = 14 if latest_application.rating_given else 180
        time_passed = local_now() - latest_application.time_created
        return time_passed > timedelta(days=waiting_period_days)

    @property
    def application_year(self):
        if self.activity == 'winter_school':
            return ws_year()
        else:
            return local_date().year

    @property
    def num_chairs(self):
        return perm_utils.num_chairs(self.activity)

    @property
    def model(self):
        """ Return the application model for this activity type.

        The model will be None if no application exists for the activity.
        """
        if hasattr(self, '_model'):
            return self._model
        self._model = models.LeaderApplication.model_from_activity(self.activity)
        return self._model

    def joined_queryset(self):
        """ Return applications, joined with commonly used attributes.

        Warning: Will raise an AttributeError if self.model failed to find
        an application type.
        """
        applications = self.model.objects.select_related('participant')
        return applications.prefetch_related('participant__leaderrecommendation_set',
                                             'participant__leaderrating_set')


class RatingsRecommendationsMixin(object):
    """ Query tools for counting ratings & recs for LeaderApplications.

    Requires self.chair to to be a Participant object (that chairs the activity).
    """

    @property
    def gave_rec(self):
        """ Select applications where the chair gave a recommendation. """
        return Q(
            participant__leaderrecommendation__time_created__gte=F('time_created'),
            participant__leaderrecommendation__activity=self.activity,
            participant__leaderrecommendation__creator=self.chair,
        )

    @property
    def gave_rating(self):
        """ Select applications where a rating was created after app creation. """
        return Q(
            participant__leaderrating__time_created__gte=F('time_created'),
            participant__leaderrating__activity=self.activity,
            participant__leaderrating__active=True,
        )

    def sum_annotation(self, selector):
        return Sum(
            Case(When(selector, then=1),
                 default=0,
                 output_field=IntegerField())
        )


class ApplicationManager(LeaderApplicationMixin, RatingsRecommendationsMixin):
    """ Leader applications for an activity, to be displayed to the chair. """

    def __init__(self, *args, **kwargs):
        # Set only if defined (so subclassas can instead define with @property)
        # Also, pop from kwargs so object.__init__ doesn't error out
        if 'chair' in kwargs:
            self.chair = kwargs.pop('chair')  # <Participant>
        if 'activity' in kwargs:
            self.activity = kwargs.pop('activity')

        return super().__init__(*args, **kwargs)

    def sorted_applications(self, just_this_year=False):
        """ Sort all applications by order of attention they need. """
        applications = self.joined_queryset()
        if just_this_year:
            applications = applications.filter(year=self.application_year)

        # Identify which have ratings and/or the leader's recommendation
        applications = applications.annotate(
            num_ratings=self.sum_annotation(self.gave_rating),
            num_recs=self.sum_annotation(self.gave_rec)
        )
        return applications.distinct().order_by('num_ratings', 'num_recs', 'time_created')

    def pending_applications(self, just_this_year=True):
        """ All applications which do not yet have a rating.

        Includes applications which should be given a recommendation first as
        well as applications that are merely awaiting a chair rating.
        """
        # Cache, because we call this twice to identify which need recs/ratings
        cache_key = '_pending_{}_year'.format('this' if just_this_year else 'any')
        if self.model is None:
            return []
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        pending = self.sorted_applications(just_this_year).filter(num_ratings=0)
        setattr(self, cache_key, pending)
        return pending

    def needs_rec(self, just_this_year=True):
        """ Applications which need to be given a rating by the viewing chair.

        If there's only one chair, then this will be a blank list (it makes no sense
        for a chair to make recommendations whene there are no co-chairs to heed
        those recommendations).
        """
        if self.model is None or self.num_chairs < 2:
            return []

        return self.pending_applications(just_this_year).filter(num_recs=0)

    def needs_rating(self, just_this_year=True):
        """ Return applications which need a rating, but not a recommendation.

        When there are multiple chairs, we count certain applications as
        needing a recommendation first. It's true that these applications need
        a rating as well, but we don't want to double count.
        """
        pending = self.pending_applications(just_this_year)
        if self.num_chairs > 1:
            return pending.filter(num_recs__gt=0)
        else:
            return pending
