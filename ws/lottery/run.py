from datetime import datetime
import io
import logging
from pathlib import Path

from ws import models
from ws.utils.dates import local_now, closest_wed_at_noon
from ws import settings
from ws.lottery.handle import SingleTripParticipantHandler, WinterSchoolParticipantHandler
from ws.lottery.rank import SingleTripParticipantRanker, WinterSchoolParticipantRanker


class LotteryRunner:
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

    def __call__(self):
        if self.trip.algorithm != 'lottery':
            self.log_stream.close()
            return

        self.logger.info("Randomly ordering (preference to MIT affiliates)...")
        ranked_participants = SingleTripParticipantRanker(self.trip)
        self.logger.info("Participants will be handled in the following order:")
        max_len = max(len(par.name) for par in ranked_participants)
        for i, par in enumerate(ranked_participants, start=1):
            affiliation = par.get_affiliation_display()
            self.logger.info(f"{i:3}. {par.name:{max_len + 3}} ({affiliation})")

        self.logger.info(50 * '-')
        for participant in ranked_participants:
            par_handler = SingleTripParticipantHandler(participant, self, self.trip)
            par_handler.place_participant()

        self.trip.algorithm = 'fcfs'
        self.trip.lottery_log = self.log_stream.getvalue()
        self.log_stream.close()
        self.trip.save()


class WinterSchoolLotteryRunner(LotteryRunner):
    def __init__(self):
        self.ranker = WinterSchoolParticipantRanker()
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
        for participant in self.ranker:
            handling_text = f"Handling {participant}"
            self.logger.debug(handling_text)
            self.logger.debug('-' * len(handling_text))
            par_handler = WinterSchoolParticipantHandler(participant, self)
            par_handler.place_participant()
