from datetime import date

from django.db.models import Q

from ws import enums, models
from ws.utils.signups import add_to_waitlist


def par_is_driver(participant):
    try:
        return participant.lotteryinfo.is_driver
    except models.LotteryInfo.DoesNotExist:
        return False


def ranked_signups(participant, after: date):
    """ Return all future WS signups for the participant. """
    # Only consider lottery signups for future trips
    return participant.signup_set.filter(
        on_trip=False,
        trip__algorithm='lottery',
        trip__trip_date__gt=after,
        trip__program=enums.Program.WINTER_SCHOOL.value,
    ).order_by('order', 'time_created', 'pk')


def place_on_trip(signup, logger):
    trip = signup.trip
    slots = 'slot' if trip.open_slots == 1 else 'slots'
    logger.info(f"{trip} has {trip.open_slots} {slots}, adding {signup.participant}")
    signup.on_trip = True
    signup.save()


class ParticipantHandler:
    """ Class to handle placement of a single participant or pair. """

    is_driver_q = Q(participant__lotteryinfo__car_status__in=['own', 'rent'])

    def __init__(self, participant, runner, min_drivers=2, allow_pairs=True):
        self.participant = participant
        self.runner = runner
        self.min_drivers = min_drivers
        self.allow_pairs = allow_pairs

        self.slots_needed = len(self.to_be_placed)

    @property
    def logger(self):
        """ All logging is routed through the runner's logger. """
        return self.runner.logger

    @property
    def is_driver(self):
        return any(par_is_driver(par) for par in self.to_be_placed)

    @property
    def paired(self):
        """ Efficiently return if this participant is reciprocally paired.

        Other methods (in models.py, and mixins.py, among other places) can
        figure out if a participant was reciprocally paired. However, these
        methods generally assume that we're only interested in a single participant.
        When running across the entire WS lottery, this results in a _lot_ of queries.

        This method accesses an annotated property defined in the ParticipantRanker.
        """
        return self.participant.reciprocally_paired

    @property
    def paired_par(self):
        try:
            return self.participant.lotteryinfo.paired_with
        except models.LotteryInfo.DoesNotExist:
            return None

    @property
    def to_be_placed(self):
        if self.allow_pairs and self.paired:
            return (self.participant, self.paired_par)
        return (self.participant,)

    @property
    def _par_text(self):
        return " + ".join(map(str, self.to_be_placed))

    def place_all_on_trip(self, signup):
        place_on_trip(signup, self.logger)
        if self.paired:
            par_signup = models.SignUp.objects.get(
                participant=self.paired_par, trip=signup.trip
            )
            place_on_trip(par_signup, self.logger)

    def _count_drivers_on_trip(self, trip) -> int:
        participant_drivers = trip.signup_set.filter(self.is_driver_q, on_trip=True)
        lottery_leaders = trip.leaders.filter(lotteryinfo__isnull=False)
        num_leader_drivers = sum(
            leader.lotteryinfo.is_driver for leader in lottery_leaders
        )
        return participant_drivers.count() + num_leader_drivers

    def _num_drivers_needed(self, trip):
        num_drivers = self._count_drivers_on_trip(trip)
        return max(self.min_drivers - num_drivers, 0)

    def bump_participant(self, signup):
        add_to_waitlist(signup, prioritize=True)
        self.logger.info("Moved %s to the top of the waitlist", signup)

    def _try_to_place(self, signup: models.SignUp) -> bool:
        """ Try to place participant (and partner) on the trip.

        Returns if successful.
        """
        trip = signup.trip
        if trip.open_slots >= self.slots_needed:
            self.place_all_on_trip(signup)
            return True
        if self.is_driver and not trip.open_slots and not self.paired:
            # A driver may displace somebody else.
            # At present, we don't allow pairs of drivers to displace 2.
            # TODO: Support the above scenario!
            if self._num_drivers_needed(trip):
                self.logger.info(
                    "%r is full, but lacks %d drivers", trip.name, self.min_drivers
                )
                signup_to_bump = self.runner.signup_to_bump(trip)
                if not signup_to_bump:
                    self.logger.info("Trip does not have a non-driver to bump")
                    return False
                self.bump_participant(signup_to_bump)
                self.logger.info(
                    "Adding driver %s to %r", signup.participant.name, trip.name
                )
                signup.on_trip = True
                signup.save()
                return True
        return False

    def place_participant(self):
        raise NotImplementedError()
        # (Place on trip or waitlist, then):
        # self.runner.mark_handled(self.participant)


class SingleTripParticipantHandler(ParticipantHandler):
    def __init__(self, participant, runner, trip):
        self.trip = trip
        allow_pairs = trip.honor_participant_pairing
        # TODO: Minimum driver requirements should be supported
        super().__init__(participant, runner, allow_pairs=allow_pairs, min_drivers=0)

    @property
    def paired(self):
        if not self.participant.reciprocally_paired:
            return False

        # A participant is only paired if both signed up for this trip
        partner_signed_up = Q(trip=self.trip, participant=self.paired_par)
        return models.SignUp.objects.filter(partner_signed_up).exists()

    def place_participant(self):
        # Indicate that this participant's number has come up!
        # (The issue of ranking is external to this module)
        self.runner.mark_seen(self.participant)

        if self.paired:
            self.logger.info(f"{self.participant} is paired with {self.paired_par}")
            if not self.runner.seen(self.paired_par):
                self.logger.info(f"Will handle signups when {self.paired_par} comes")
                return

        # Try to place all participants, otherwise add them to the waitlist
        signup = models.SignUp.objects.get(participant=self.participant, trip=self.trip)
        if not self._try_to_place(signup):
            for par in self.to_be_placed:
                self.logger.info(f"Adding {par.name} to the waitlist")
                add_to_waitlist(
                    models.SignUp.objects.get(trip=self.trip, participant=par)
                )
        self.runner.mark_handled(self.participant)
        if self.paired_par:
            self.runner.mark_handled(self.paired_par)


class WinterSchoolParticipantHandler(ParticipantHandler):
    def __init__(self, participant, runner):
        """
        :param runner: An instance of LotteryRunner
        """
        self.lottery_rundate = runner.execution_datetime.date()
        super().__init__(participant, runner, min_drivers=2, allow_pairs=True)

    def bump_participant(self, signup):
        """ Try to place a bumped participant on a trip before waitlisting them.

        If a participant is placed on a trip, but later bumped off that trip to
        make room for a driver, we can generally assume that they would prefer
        a definite spot on one of their ranked trips as opposed to being on
        the waitlist.

        Note that this is a different participant than the one being handled!
        """
        # This participant is currently on the trip!
        assert signup.on_trip
        par = signup.participant

        self.logger.info("Bumping %s off %s", par.name, signup.trip.name)

        # Paired participants would generally prefer to stick together
        try:
            lotteryinfo = par.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            pass  # Definitely not paired.
        else:
            # Choose to just stay on the waitlist in hopes of joining their partner
            # NOTE: (cannot use `reciprocally_paired`, since that's a rank-annotated prop)
            if lotteryinfo.reciprocally_paired_with:
                super().bump_participant(signup)
                return

        self.logger.debug("Searching all signups for a potentially open trip.")
        # Do not bother being picky about potentially being bumped by a driver
        future_signups = ranked_signups(par, after=self.lottery_rundate)
        for other_signup in future_signups.exclude(pk=signup.pk):
            if not other_signup.trip.open_slots:
                self.logger.debug("%r is full", other_signup.trip.name)
                continue
            place_on_trip(other_signup, self.logger)
            self.logger.debug("Placed on %r", other_signup.trip.name)
            signup.on_trip = False
            signup.save()
            return

        # No slots are open - just waitlist them on their top trip!
        super().bump_participant(signup)

    def future_signups(self):
        signups = ranked_signups(self.participant, after=self.lottery_rundate)
        if self.paired:  # Restrict signups to those both signed up for
            signups = signups.filter(trip__in=self.paired_par.trip_set.all())
        return signups

    def place_participant(self):
        # Indicate that this participant's number has come up!
        # (The issue of ranking is external to this module)
        self.runner.mark_seen(self.participant)

        if self.paired:
            self.logger.info(f"{self.participant} is paired with {self.paired_par}")
            if not self.runner.seen(self.paired_par):
                self.logger.info(f"Will handle signups when {self.paired_par} comes")
                return None

        info = self._place_or_waitlist()
        self.runner.mark_handled(self.participant)
        if self.paired_par:
            self.runner.mark_handled(self.paired_par)

        return info

    def _placement_would_jeopardize_driver_bump(self, signup):
        """ Return if placing this participant (or pair) risks them later being bumped.

        For paired participants, this returns true if 2 slots remain & at least
        one more driver is required.

        This is invoked for every signup, so we make attempts to exit early
        (for efficiency) in most scenarios.
        """
        open_slots = signup.trip.open_slots

        if open_slots < self.slots_needed:
            return False  # Cannot place anyway, driver has nothing to do with it.

        # Shortcut - if we're not taking the last places, we needn't query driver status
        future_num_slots = open_slots - self.slots_needed
        if future_num_slots > self.min_drivers:
            return False  # Definitely will not be bumped (enough slots remain)

        if self.is_driver:
            return False  # A driver bumping a driver never makes sense.

        # At this point, few slots remain. Participant could potentially risk being bumped!
        num_drivers_needed = self._num_drivers_needed(signup.trip)
        if not num_drivers_needed:
            return False  # We have enough drivers already!

        # Few slots remain, but it's possible we already have 1 driver on the trip.
        # Use case: 2 slots left, 1 driver needed. We can safely take second-to-last spot.
        if num_drivers_needed <= future_num_slots:
            return False

        # At this point, potential drivers could bump some of the last signups!
        # If other unhandled participants ranked this trip, consider it jeopardized
        driver_signups = models.SignUp.objects.filter(
            trip=signup.trip,
            on_trip=False,  # If on the trip, we know they're handled.
            participant__lotteryinfo__car_status__in=['own', 'rent'],
            # TODO (Django 2): Exclude reciprocally-paired participants where both are signed up.
            # These participants cannot bump.
            # This is simpler in Django 2 (see `annotate_reciprocally_paired()`)
        ).exclude(participant_id__in=self.to_be_placed)

        return any(
            not self.runner.handled(signup.participant) for signup in driver_signups
        )

    def _place_or_waitlist(self):
        future_signups = self.future_signups()

        # JSON-serializable object we can use to analyze outputs.
        info = {
            'participant_pk': self.participant.pk,
            'paired_with_pk': self.paired_par and self.paired_par.pk,
            'is_paired': bool(self.paired),
            'affiliation': self.participant.affiliation,
            'ranked_trips': [signup.trip_id for signup in future_signups],
            'placed_on_choice': None,  # One-indexed rank
            'waitlisted': False,
        }

        if not future_signups:
            self.logger.info("%s did not choose any trips this week", self._par_text)
            return info

        # Try to place participants on their first choice available trip
        skipped_to_avoid_driver_bump = []  # type: Tuple[int, models.SignUp]
        for rank, signup in enumerate(future_signups, start=1):
            trip_name = signup.trip.name
            if self._placement_would_jeopardize_driver_bump(signup):
                self.logger.debug("Placing on %r risks bump from a driver", trip_name)
                skipped_to_avoid_driver_bump.append((rank, signup))
                continue
            if self._try_to_place(signup):
                self.logger.debug(f"Placed on trip #{rank} of {len(future_signups)}")
                return {**info, 'placed_on_choice': rank}
            self.logger.info("Can't place %s on %r", self._par_text, trip_name)

        # At this point, there were no trips that could take the participant or pair
        # It's possible that some were skipped because few spaces remained & a driver may bump.
        # If any potential placements remain, take those & risk a future bump.
        for rank, signup in skipped_to_avoid_driver_bump:
            if self._try_to_place(signup):
                self.logger.debug(f"Placed on trip #{rank} of {len(future_signups)}")
                return {**info, 'placed_on_choice': rank}

        self.logger.info(f"None of {self._par_text}'s trips are open.")
        favorite_trip = future_signups.first().trip
        for participant in self.to_be_placed:
            favorite_signup = models.SignUp.objects.get(
                participant=participant, trip=favorite_trip
            )
            add_to_waitlist(favorite_signup)
            with_email = f"{self._par_text} ({participant.email})"
            self.logger.info(f"Waitlisted {with_email} on {favorite_trip.name}")

        return {**info, 'waitlisted': True}
