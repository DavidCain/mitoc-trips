import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q

import ws.utils.dates as date_utils
from ws import models, settings

logger = logging.getLogger(__name__)


def lapsed_participants():
    """Return all participants who've not used the system in a long time.

    We exclude anybody who's signed a waiver, paid dues, been on trips, or
    updated their profile recently. We consider a number of factors for
    "activity" so as to minimize the chance that we accidentally consider
    somebody to have lapsed.
    """
    now = date_utils.local_now()
    one_year_ago = now - timedelta(days=365)

    # Participants are required to update their info periodically
    # If a sufficient period of time has lapsed since they last updated,
    # we can deduce that they're likely not going on trips anymore
    multiple_update_periods = timedelta(days=(2.5 * settings.MUST_UPDATE_AFTER_DAYS))
    lapsed_update = Q(profile_last_updated__lt=(now - multiple_update_periods))

    today = now.date()
    active_members = (
        # Anybody with a current membership/waiver is active
        Q(membership__membership_expires__gte=today)
        | Q(membership__waiver_expires__gte=today)
        |
        # Anybody who led or participated in a trip during the last year
        Q(trips_led__trip_date__gte=one_year_ago)
        | Q(trip__trip_date__gte=one_year_ago)
        |
        # Anybody signed up for a trip in the future
        # (Should be disallowed without a current waiver, but might as well check)
        Q(signup__trip__trip_date__gte=today)
    )

    return models.Participant.objects.filter(lapsed_update).exclude(active_members)


def purge_non_student_discounts():
    """Purge non-students from student-only discounts.

    Student eligibility is enforced at the API and form level. If somebody was
    a student at the time of enrolling but is no longer a student, we should
    unenroll them.
    """
    stu_discounts = models.Discount.objects.filter(student_required=True)
    not_student = ~Q(affiliation__in=models.Participant.STUDENT_AFFILIATIONS)

    # Remove student discounts from all non-students who have them
    participants = models.Participant.objects.all()
    for par in participants.filter(not_student, discounts__in=stu_discounts):
        par.discounts.set(par.discounts.filter(student_required=False))


@transaction.atomic
def purge_old_medical_data():
    """For privacy reasons, purge old medical information.

    We have a lot of people's medical information in our system.
    However, many people leave Boston, graduate MIT, or otherwise
    just move on from the club. There's no reason for us to store old
    information in our system. To safeguard participant privacy, we should
    remove information that we do not need.

    It's not the worst outcome if we accidentally purge medical information for
    an active participant, since that will just require them to provide current
    medical info.
    """
    needs_scrub = (
        lapsed_participants()
        # We only update participants that have emergency info & have not yet been scrubbed
        .exclude(emergency_info__allergies='').exclude(emergency_info=None)
        # If some other query already holds a lock, just skip for now!
        # (likely means that the participant is being updated, and shouldn't be purged)
        # We can always try to purge again on the next scheduled run.
        # TODO (Django 2), exclusive join *only* on Participant + e. info, not Membership
        # .select_for_update(skip_locked=True, of=('self', 'emergency_info'))
    )

    # Re-select participants, this time with an UPDATE lock (skirts Django shortcoming)
    # NOTE: This technically means that participants could have changed in this window.
    # TODO (Django 2): Remove this hack, use above `of=` solution
    needs_scrub = (
        models.Participant.objects.filter(pk__in=needs_scrub).select_related(
            'emergency_info'
        )
        # If some other query already holds a lock, just skip for now!
        # (likely means that the participant is being updated, and shouldn't be purged)
        # We can always try to purge again on the next scheduled run.
        .select_for_update(skip_locked=True)
    )

    for par in needs_scrub:
        logger.info(
            "Purging medical data for %s (%s - %s, last updated %s)",
            par.name,
            par.pk,
            par.email,
            par.profile_last_updated.date(),
        )

    # Using update() bypasses normal model validation that these be non-empty.
    # SQL constraints prevent `null` values, but we can have empty strings!
    models.EmergencyInfo.objects.filter(participant__in=needs_scrub).update(
        allergies="", medications="", medical_history=""
    )
