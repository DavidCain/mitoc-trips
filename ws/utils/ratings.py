from ws import models
from django.db.models import Q


def deactivate_ratings(participant, activity):
    """ Mark any existing ratings for the activity as inactive. """
    find_ratings = {'participant__pk': participant.pk,
                    'activity': activity,
                    'active': True}
    for existing in models.LeaderRating.objects.filter(Q(**find_ratings)):
        existing.active = False
        existing.save()
