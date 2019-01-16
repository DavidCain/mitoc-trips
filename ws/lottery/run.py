from datetime import datetime
import io
import json
import logging
from pathlib import Path

from mitoc_const import affiliations

from ws import models
from ws.utils.dates import local_date, local_now, closest_wed_at_noon
from ws import settings
from ws.lottery.handle import SingleTripParticipantHandler, WinterSchoolParticipantHandler
from ws.lottery.rank import SingleTripParticipantRanker, WinterSchoolParticipantRanker


AFFILIATION_MAPPING = {
    # Excludes the deprecated student code, since new members don't have that
    aff.CODE: aff.VALUE for aff in affiliations.ALL
}


class LotteryRunner:
    """ Parent class for a lottery executor.

    Instances of this class may be executed to perform the lottery mechanism
    for one or more trips.
    """
    def __init__(self):
        # Get a logger instance that captures activity for _just_ this run
        self.logger = logging.getLogger(self.logger_id)
        self.logger.setLevel(logging.DEBUG)

        self.participants_handled = {}  # Key: primary keys, gives boolean if handled

    @property
    def logger_id(self):
        """ Get a unique logger object per each instance. """
        return f"{__name__}.{id(self)}"

    def handled(self, participant):
        return self.participants_handled.get(participant.pk, False)

    def mark_handled(self, participant, handled=True):
        self.participants_handled[participant.pk] = handled

    def participant_to_bump(self, trip):
        """ Which participant to bump off the trip if another needs a place.

        By default, just goes with the most recently-added participant.
        Standard us case: Somebody needs to be bumped so a driver may join.
        """
        on_trip = trip.signup_set.filter(on_trip=True)
        return on_trip.order_by('-last_updated').first()

    def __call__(self):
        raise NotImplementedError("Subclasses must implement lottery behavior")


class SingleTripLotteryRunner(LotteryRunner):
    """ Place participants vying for spots on a single trip. """
    def __init__(self, trip):
        self.trip = trip
        super().__init__()
        self.configure_logger()

    @property
    def logger_id(self):
        """ Get a constant logger identifier for each trip. """
        return f"{__name__}.trip.{self.trip.pk}"

    def configure_logger(self):
        """ Configure a stream to save the log to the trip. """
        self.log_stream = io.StringIO()

        self.handler = logging.StreamHandler(stream=self.log_stream)
        self.handler.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

    def _make_fcfs(self):
        """ After lottery execution, mark the trip FCFS & write out the log. """
        self.trip.algorithm = 'fcfs'
        self.trip.lottery_log = self.log_stream.getvalue()
        self.log_stream.close()
        self.trip.save()

    def __call__(self):
        if self.trip.algorithm != 'lottery':
            self.log_stream.close()
            return

        self.logger.info("Randomly ordering (preference to MIT affiliates)...")
        ranked_participants = list(SingleTripParticipantRanker(self.trip))

        if not ranked_participants:
            self.logger.info("No participants signed up.")
            self.logger.info("Converting trip to first-come, first-serve.")
            self._make_fcfs()
            return

        self.logger.info("Participants will be handled in the following order:")
        max_len = max(len(par.name) for par, _ in ranked_participants)
        for i, (par, key) in enumerate(ranked_participants, start=1):
            affiliation = par.get_affiliation_display()
            # pylint: disable=logging-fstring-interpolation
            self.logger.info(f"{i:3}. {par.name:{max_len + 3}} ({affiliation}, {key})")

        self.logger.info(50 * '-')
        for participant, _ in ranked_participants:
            par_handler = SingleTripParticipantHandler(participant, self, self.trip)
            par_handler.place_participant()
        self._make_fcfs()

class WinterSchoolLotteryRunner(LotteryRunner):
    def __init__(self, execution_date=None):
        self.execution_date = execution_date or local_date()
        self.ranker = WinterSchoolParticipantRanker(self.execution_date)
        super().__init__()
        self.configure_logger()

    def configure_logger(self):
        """ Configure a stream to save the log to the trip. """
        datestring = datetime.strftime(local_now(), "%Y-%m-%dT:%H:%M:%S")
        filename = Path(settings.WS_LOTTERY_LOG_DIR, f"ws_{datestring}.log")
        self.handler = logging.FileHandler(filename)
        self.handler.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)

    def __call__(self):
        self.logger.info("Running the Winter School lottery for %s",
                         self.execution_date)
        self.assign_trips()
        self.free_for_all()
        self.handler.close()

    def free_for_all(self):
        """ Make trips first-come, first-serve.

        Trips re-open Wednesday at noon, close at midnight on Thursday.
        """
        self.logger.info("Making all lottery trips first-come, first-serve")
        ws_trips = models.Trip.objects.filter(activity='winter_school')
        noon = closest_wed_at_noon()
        for trip in ws_trips.filter(algorithm='lottery'):
            trip.make_fcfs(signups_open_at=noon)
            trip.save()

    def participant_to_bump(self, trip):
        return self.ranker.lowest_non_driver(trip)

    def assign_trips(self):
        num_participants = self.ranker.participants_to_handle().count()
        self.logger.info("%s participants signed up for trips this week", num_participants)
        for global_rank, (participant, key) in enumerate(self.ranker, start=1):
            # get_affiliation_display() includes extra explanatory text we don't need
            affiliation = AFFILIATION_MAPPING[participant.affiliation]
            handling_header = [f"\nHandling {participant}", f"({affiliation}, {key})"]
            self.logger.debug('\n'.join(handling_header))
            self.logger.debug('-' * max(len(line) for line in handling_header))
            par_handler = WinterSchoolParticipantHandler(participant, self)

            json_result = par_handler.place_participant()
            if json_result is not None:
                json_result['global_rank'] = global_rank
                json_result['has_flaked'] = key.flake_factor > 0
                self.logger.debug("RESULT: %s", json.dumps(json_result))
