from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, TestCase

from ws import decorators
from ws.tests import factories


class GroupRequiredTest(TestCase):
    def test_single_group_required(self) -> None:
        """Reproduce a bug that only happened if groups had name collisions.

        Specifically, we accidentally used substring comparison when we
        meant to do exact string matching!

        If a view was marked as requiring a *single* group, we accidentally
        failed to convert that one string to a *collection* of strings, but
        because Python strings *are* collections of strings... it "worked."

        We never had access issues becaus the few groups we use are unique.
        """
        docs = Group.objects.create(name="leaders_with_medical_degrees")
        # Not a real group, but using this to demonstrate a bug!
        leaders = Group.objects.get(name="leaders")

        @decorators.group_required("leaders_with_medical_degrees")
        def mds_only(request: HttpRequest) -> HttpResponse:
            return HttpResponse()

        participant = factories.ParticipantFactory.create()
        leaders.user_set.add(participant.user)

        request = RequestFactory().get("/")
        request.user = participant.user
        request.participant = participant  # type: ignore[attr-defined]

        with self.assertRaises(PermissionDenied):
            mds_only(request)

        docs.user_set.add(participant.user)
        mds_only(request)
