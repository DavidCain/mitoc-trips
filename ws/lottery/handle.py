from django.db.models import Q

from ws.utils.dates import local_date
from ws.utils.signups import add_to_waitlist
from ws import models


def par_is_driver(participant):
    try:
        return participant.lotteryinfo.is_driver
    except models.LotteryInfo.DoesNotExist:
        return False


def place_on_trip(signup, logger):
    trip = signup.trip
    slots = ' slot' if trip.open_slots == 1 else 'slots'
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
        else:
            return (self.participant,)

    @property
    def par_text(self):
        return " + ".join(map(str, self.to_be_placed))

    def place_all_on_trip(self, signup):
        place_on_trip(signup, self.logger)
        if self.paired:
            par_signup = models.SignUp.objects.get(participant=self.paired_par,
                                                   trip=signup.trip)
            place_on_trip(par_signup, self.logger)

    def count_drivers_on_trip(self, trip):
        participant_drivers = trip.signup_set.filter(self.is_driver_q, on_trip=True)
        lottery_leaders = trip.leaders.filter(lotteryinfo__isnull=False)
        num_leader_drivers = sum(leader.lotteryinfo.is_driver
                                 for leader in lottery_leaders)
        return participant_drivers.count() + num_leader_drivers

    def try_to_place(self, signup):
        """ Try to place participant (and partner) on the trip.

        Returns if successful.
        """
        trip = signup.trip
        if trip.open_slots >= self.slots_needed:
            self.place_all_on_trip(signup)
            return True
        elif self.is_driver and not trip.open_slots and not self.paired:
            # A driver may displace somebody else
            # (but a couple with a driver cannot displace two people)
            if self.count_drivers_on_trip(trip) < self.min_drivers:
                self.logger.info(f"{trip} is full, but doesn't have {self.min_drivers} drivers")
                self.logger.info(f"Adding {signup} to '{trip}', as they're a driver")
                par_to_bump = self.runner.participant_to_bump(trip)
                add_to_waitlist(par_to_bump, prioritize=True)
                self.logger.info(f"Moved {par_to_bump} to the top of the waitlist")
                # TODO: Try to move the bumped participant to a preferred, open trip!
                signup.on_trip = True
                signup.save()
                return True
        return False

    def place_participant(self):
        raise NotImplementedError()
        # (Place on trip or waitlist, then):
        #self.runner.mark_handled(self.participant)


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
        if self.paired:
            self.logger.info(f"{self.participant} is paired with {self.paired_par}")
            if not self.runner.handled(self.paired_par):
                self.logger.info(f"Will handle signups when {self.paired_par} comes")
                self.runner.mark_handled(self.participant)
                return

        # Try to place all participants, otherwise add them to the waitlist
        signup = models.SignUp.objects.get(participant=self.participant,
                                           trip=self.trip)
        if not self.try_to_place(signup):
            for par in self.to_be_placed:
                self.logger.info(f"Adding {par.name} to the waitlist")
                add_to_waitlist(models.SignUp.objects.get(trip=self.trip,
                                                          participant=par))
        self.runner.mark_handled(self.participant)


class WinterSchoolParticipantHandler(ParticipantHandler):
    def __init__(self, participant, runner):
        """
        :param runner: An instance of LotteryRunner
        """
        self.today = local_date()
        super().__init__(participant, runner, min_drivers=2, allow_pairs=True)

    @property
    def future_signups(self):
        # Only consider lottery signups for future trips
        signups = self.participant.signup_set.filter(
            trip__trip_date__gt=self.today,
            trip__algorithm='lottery',
            trip__activity='winter_school'
        )
        if self.paired:  # Restrict signups to those both signed up for
            signups = signups.filter(trip__in=self.paired_par.trip_set.all())
        return signups.order_by('order', 'time_created')

    def place_participant(self):
        if self.paired:
            self.logger.info(f"{self.participant} is paired with {self.paired_par}")
            if not self.runner.handled(self.paired_par):
                self.logger.info(f"Will handle signups when {self.paired_par} comes")
                self.runner.mark_handled(self.participant)
                return
        if not self.future_signups:
            self.logger.info(f"{self.par_text} did not choose any trips this week")
            self.runner.mark_handled(self.participant)
            return

        # Try to place participants on their first choice available trip
        for signup in self.future_signups:
            if self.try_to_place(signup):
                break
            else:
                self.logger.info(f"Can't place {self.par_text} on {signup.trip}")

        else:  # No trips are open
            self.logger.info(f"None of {self.par_text}'s trips are open.")
            favorite_trip = self.future_signups.first().trip
            for participant in self.to_be_placed:
                find_signup = Q(participant=participant, trip=favorite_trip)
                favorite_signup = models.SignUp.objects.get(find_signup)
                add_to_waitlist(favorite_signup)
                with_email = f"{self.par_text} ({participant.email})"
                self.logger.info(f"Waitlisted {with_email} on {favorite_signup.trip.name}")

        self.runner.mark_handled(self.participant)
