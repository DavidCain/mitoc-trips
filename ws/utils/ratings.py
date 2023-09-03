from collections.abc import Iterable
from typing import TYPE_CHECKING, TypedDict

from django.contrib.auth.models import User
from django.db.models import Case, F, IntegerField, Q, QuerySet, Sum, When

import ws.utils.perms as perm_utils
from ws import enums, models


class RatingsAndRecsCounted(TypedDict):
    num_ratings: int
    num_recs: int


if TYPE_CHECKING:
    from django_stubs_ext import WithAnnotations

    from ws.models import LeaderApplication

    AnnotatedApplication = WithAnnotations[LeaderApplication, RatingsAndRecsCounted]
else:
    AnnotatedApplication = object


def deactivate_ratings(participant, activity):
    """Mark any existing ratings for the activity as inactive."""
    find_ratings = Q(participant__pk=participant.pk, activity=activity, active=True)
    for existing in models.LeaderRating.objects.filter(find_ratings):
        existing.active = False
        existing.save()


class LeaderApplicationMixin:
    """Some common tools for interacting with LeaderApplication objects."""

    @property
    def activity_enum(self) -> enums.Activity:
        raise NotImplementedError

    def activity_chairs(self) -> QuerySet[User]:
        """Return the chairs for this activity."""

        # It's important that this remain a method, not stored at init.
        # This way, views that want to get activity from self.kwargs can inherit from the mixin
        return perm_utils.activity_chairs(self.activity_enum)

    # The model is meant to be a class attribute of SingleObjectMixin
    @property
    def model(self) -> type[models.LeaderApplication]:
        """Return the application model for this activity type.

        The model will be None if no application exists for the activity.
        """
        model = models.LeaderApplication.model_from_activity(self.activity_enum)
        assert model is not None, "Unexpectedly got an application-less activity!"
        return model

    def joined_queryset(self):
        """Return applications, joined with commonly used attributes.

        Warning: Will raise an AttributeError if self.model failed to find
        an application type.
        """
        applications = self.model.objects.select_related('participant')
        return applications.prefetch_related(
            'participant__leaderrecommendation_set', 'participant__leaderrating_set'
        )


class RatingsRecommendationsMixin:
    """Query tools for counting ratings & recs for LeaderApplications.

    Requires self.chair to to be a Participant object (that chairs the activity).
    """

    @property
    def gave_rec(self):
        """Select applications where the chair gave a recommendation."""
        return Q(
            participant__leaderrecommendation__time_created__gte=F('time_created'),
            participant__leaderrecommendation__activity=self.activity_enum.value,
            participant__leaderrecommendation__creator=self.chair,
        )

    @property
    def gave_rating(self):
        """Select applications where a rating was created after app creation."""
        return Q(
            # NOTE: Rating doesn't need to be active (if the leader was
            # deactivated, we don't want their application to re-appear)
            participant__leaderrating__time_created__gte=F('time_created'),
            participant__leaderrating__activity=self.activity_enum.value,
        )

    @staticmethod
    def sum_annotation(selector):
        # Django 2.0: Use conditional aggregation instead
        return Sum(Case(When(selector, then=1), default=0, output_field=IntegerField()))


class ApplicationManager(LeaderApplicationMixin, RatingsRecommendationsMixin):
    """Leader applications for an activity, to be displayed to the chair."""

    def __init__(self, *args, **kwargs):
        # Set only if defined (so subclasses can instead define with @property)
        # Also, pop from kwargs so object.__init__ doesn't error out
        if 'chair' in kwargs:
            self.chair = kwargs.pop('chair')  # <Participant>
        if 'activity_enum' in kwargs:
            self.activity_enum = kwargs.pop('activity_enum')
        assert not kwargs, "Kwargs should be pruned to use the mixin pattern"

        super().__init__(*args, **kwargs)

    @property
    def activity_enum(self) -> enums.Activity:
        return self._activity_enum

    @activity_enum.setter
    def activity_enum(self, value: enums.Activity) -> None:
        self._activity_enum = value

    def sorted_annotated_applications(self) -> QuerySet[AnnotatedApplication]:
        """Sort all applications by order of attention they need."""
        # Identify which have ratings and/or the leader's recommendation
        applications: QuerySet[AnnotatedApplication] = self.joined_queryset().annotate(
            num_ratings=self.sum_annotation(self.gave_rating),
            num_recs=self.sum_annotation(self.gave_rec),
        )
        return applications.distinct().order_by(
            '-archived', 'num_ratings', 'num_recs', 'time_created'
        )

    def pending_applications(self) -> list[AnnotatedApplication]:
        """All applications which do not yet have a rating.

        NOTE: This immediately queries the database. If you need to deal with
        past applications in addition to pending ones, it's recommended to call
        sorted_annotated_applications() and then do Python-based filtering from
        there.

        Includes applications which should be given a recommendation first as
        well as applications that are merely awaiting a chair rating.
        """
        # Some activities don't actually have an application type defined! (e.g. 'cabin')
        # Exit early so we don't fail trying to build a database query
        if not models.LeaderApplication.can_apply_for_activity(self.activity_enum):
            return []

        return list(
            self.sorted_annotated_applications()
            .filter(num_ratings=0)
            .exclude(archived=True)
        )

    @staticmethod
    def _chair_should_recommend(app: AnnotatedApplication) -> bool:
        """Return if the chair should be expected to recommend this application.

        This determines where the application appears in the queue of pending
        applications (assuming it's a pending application in the first place!).
        """
        if app.archived:  # The application is no longer pending
            return False
        if app.num_recs:  # The chair has already made a recommendation
            return False
        if app.num_ratings:  # The application received a rating
            return False
        return True

    def needs_rec(
        self,
        applications: Iterable[AnnotatedApplication],
    ) -> list[AnnotatedApplication]:
        """Applications which need to be given a rating by the viewing chair.

        If there's only one chair, then this will be a blank list (it makes no sense
        for a chair to make recommendations when there are no co-chairs to heed
        those recommendations).
        """
        if not models.LeaderApplication.can_apply_for_activity(self.activity_enum):
            return []
        if len(self.activity_chairs()) < 2:
            return []

        return [app for app in applications if self._chair_should_recommend(app)]

    def _should_rate(self, app: AnnotatedApplication) -> bool:
        if app.archived:  # The application is no longer pending
            return False
        if app.num_ratings:  # The application received a rating
            return False
        # If there are multiple chairs, we request recommendations first
        if len(self.activity_chairs()) > 1:
            return bool(app.num_recs)
        return True

    def needs_rating(
        self, applications: Iterable[AnnotatedApplication]
    ) -> list[AnnotatedApplication]:
        """Return applications which need a rating, but not a recommendation.

        When there are multiple chairs, we count certain applications as
        needing a recommendation first. It's true that these applications need
        a rating as well, but we don't want to double count.
        """
        return [app for app in applications if self._should_rate(app)]
