from datetime import datetime

from django.contrib.syndication.views import Feed
from django.db.models import QuerySet
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from ws.models import Trip
from ws.utils.dates import local_date

DEFAULT_TIMEZONE = timezone.get_default_timezone()  # (US/Eastern)


class UpcomingTripsFeed(Feed):
    title = "MITOC Trips"
    link = reverse_lazy("trips")
    description = "Upcoming trips by the MIT Outing Club"

    def items(self) -> QuerySet[Trip]:
        return Trip.objects.filter(trip_date__gte=local_date()).order_by("-trip_date")

    def item_title(self, item: Trip) -> str:
        return item.name

    def item_description(self, item: Trip) -> str:
        return item.description

    def item_link(self, item: Trip) -> str:
        return reverse("view_trip", args=[item.pk])

    def item_pubdate(self, item: Trip) -> datetime:
        return item.time_created.astimezone(DEFAULT_TIMEZONE)

    def item_author_name(self, item: Trip) -> str:
        return item.creator.name

    def item_updateddate(self, item: Trip) -> datetime:
        return item.last_edited.astimezone(DEFAULT_TIMEZONE)
