from datetime import timedelta

from django.db.models import Case, F, IntegerField, Q, Sum, When

import ws.utils.perms as perm_utils
from ws import models
from ws.utils.dates import local_date, local_now, ws_year


def deactivate_ratings(participant, activity):
    """ Mark any existing ratings for the activity as inactive. """
    find_ratings = {
        'participant__pk': participant.pk,
        'activity': activity,
        'active': True,
    }
    for existing in models.LeaderRating.objects.filter(Q(**find_ratings)):
        existing.active = False
        existing.save()


class LeaderApplicationMixin:
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
        """ Return the number of chairs for this activity. """

        # It's important that this remain a property (dynamically requested, not stored at init)
        # This way, views that want to get activity from self.kwargs can inheret from the mixin
        if not hasattr(self, '_num_chairs'):
            self._num_chairs = perm_utils.num_chairs(self.activity)
        return self._num_chairs

    @property
    def model(self):
        """ Return the application model for this activity type.

        The model will be None if no application exists for the activity.
        """
        if not hasattr(self, '_model'):
            self._model = models.LeaderApplication.model_from_activity(self.activity)
        return self._model

    def joined_queryset(self):
        """ Return applications, joined with commonly used attributes.

        Warning: Will raise an AttributeError if self.model failed to find
        an application type.
        """
        applications = self.model.objects.select_related('participant')
        return applications.prefetch_related(
            'participant__leaderrecommendation_set', 'participant__leaderrating_set'
        )


class RatingsRecommendationsMixin:
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
            # NOTE: Rating doesn't need to be active (if the leader was
            # deactivated, we don't want their application to re-appear)
            participant__leaderrating__time_created__gte=F('time_created'),
            participant__leaderrating__activity=self.activity,
        )

    def sum_annotation(self, selector):
        # Django 2.0: Use conditional aggregation instead
        return Sum(Case(When(selector, then=1), default=0, output_field=IntegerField()))


class ApplicationManager(LeaderApplicationMixin, RatingsRecommendationsMixin):
    """ Leader applications for an activity, to be displayed to the chair. """

    def __init__(self, *args, **kwargs):
        # Set only if defined (so subclasses can instead define with @property)
        # Also, pop from kwargs so object.__init__ doesn't error out
        if 'chair' in kwargs:
            self.chair = kwargs.pop('chair')  # <Participant>
        if 'activity' in kwargs:
            self.activity = kwargs.pop('activity')

        super().__init__(*args, **kwargs)

    def sorted_annotated_applications(self):
        """ Sort all applications by order of attention they need. """
        applications = self.joined_queryset()

        # Identify which have ratings and/or the leader's recommendation
        applications = applications.annotate(
            num_ratings=self.sum_annotation(self.gave_rating),
            num_recs=self.sum_annotation(self.gave_rec),
        )
        return applications.distinct().order_by(
            'num_ratings', 'num_recs', 'time_created'
        )

    def pending_applications(self):
        """ All applications which do not yet have a rating.

        NOTE: This immediately queries the database. If you need to deal with
        past applications in addition to pending ones, it's recommended to call
        sorted_annotated_applications() and then do Python-based filtering from
        there.

        Includes applications which should be given a recommendation first as
        well as applications that are merely awaiting a chair rating.
        """
        # Some activities don't actually have an application type defined! (e.g. 'cabin')
        # Exit early so we don't fail trying to build a database query
        if self.model is None:
            return []

        return list(self.sorted_annotated_applications().filter(num_ratings=0))

    def _chair_should_recommend(self, app):
        """ Return if the chair should be expected to recommend this application.

        This determines where the application appears in the queue of pending
        applications (assuming it's a pending application in the first place!).
        """
        if app.num_recs:  # The chair has already made a recommendation
            return False
        if app.num_ratings:  # The application received a rating
            return False
        return True

    def needs_rec(self, applications):
        """ Applications which need to be given a rating by the viewing chair.

        If there's only one chair, then this will be a blank list (it makes no sense
        for a chair to make recommendations when there are no co-chairs to heed
        those recommendations).
        """
        if self.model is None or self.num_chairs < 2:
            return []

        return [app for app in applications if self._chair_should_recommend(app)]

    def _should_rate(self, app):
        if app.num_ratings:  # The application received a rating
            return False
        # If there are multiple chairs, we request recommendations first
        if self.num_chairs > 1:
            return bool(app.num_recs)
        return True

    def needs_rating(self, applications):
        """ Return applications which need a rating, but not a recommendation.

        When there are multiple chairs, we count certain applications as
        needing a recommendation first. It's true that these applications need
        a rating as well, but we don't want to double count.
        """
        return [app for app in applications if self._should_rate(app)]
