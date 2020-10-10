from datetime import date
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase
from freezegun import freeze_time
from mitoc_const import affiliations

from ws import tasks
from ws.tests import TestCase, factories
from ws.utils import member_sheets


class MutexTaskTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        patched = mock.patch('ws.tasks.cache', wraps=cache)
        self.cache = patched.start()
        self.addCleanup(patched.stop)

    def test_lock_format_default_naming(self):
        """ By default, we just use the function name as a unique lock ID. """

        @tasks.mutex_task()
        def some_unique_task_name(positional_arg):
            pass

        some_unique_task_name('a_string_argument')
        self.cache.add.assert_called_with('some_unique_task_name', 'true', 600)
        self.cache.delete.assert_called_with('some_unique_task_name')

    def test_lock_format_custom_naming(self):
        """ The decorator accepts a string that formats the task ID.

        Specifically, this decorator can access both positional arguments
        and optional arguments.
        """

        @tasks.mutex_task('{positional_arg}-{named_kwarg2}')
        def dummy_task(positional_arg, named_kwarg='123', named_kwarg2=None):
            pass

        dummy_task('hello', named_kwarg2='there')
        self.cache.add.assert_called_with('hello-there', 'true', 600)
        self.cache.delete.assert_called_with('hello-there')

    def test_lock_always_released(self):
        """ Even when raising exceptions, the lock is released. """

        @tasks.mutex_task()
        def divide(numerator, denominator):
            return numerator / denominator

        with self.assertRaises(ZeroDivisionError):
            divide(3, 0)

        self.cache.add.assert_called_with('divide', 'true', 600)
        self.cache.delete.assert_called_with('divide')

    def test_lock_already_held(self):
        """ Tasks don't execute when a lock is already held. """
        inner_logic = mock.Mock()

        @tasks.mutex_task('do_thing-{unique_id}')
        def do_thing(unique_id):
            inner_logic.run_after_lock_obtained()

        # Add a lock to the cache (as if another worker started work already)
        locked = cache.add('do_thing-123', 'true', 5)
        self.assertTrue(locked)

        do_thing(123)

        # We tried to add to the cache, but it fails, and no code is run
        self.cache.add.assert_called_with('do_thing-123', 'true', 600)
        inner_logic.run_after_lock_obtain.assert_not_called()

        # We don't touch the lock, since the other task will do its own cleanup
        self.cache.delete.assert_not_called()

        # (Remove from the cache just for cleanup)
        cache.delete('do_thing-123')


class TaskTests(TestCase):
    @staticmethod
    @mock.patch('ws.utils.member_sheets.update_discount_sheet')
    def test_update_discount_sheet(update_discount_sheet):
        discount = factories.DiscountFactory.create(pk=9123, ga_key='test-key')
        tasks.update_discount_sheet(9123)
        update_discount_sheet.assert_called_with(discount)

    @staticmethod
    @mock.patch('ws.utils.geardb.update_affiliation')
    def test_update_participant_affiliation(update_affiliation):
        participant = factories.ParticipantFactory.create(
            affiliation=affiliations.NON_AFFILIATE.CODE
        )
        tasks.update_participant_affiliation(participant.pk)
        update_affiliation.assert_called_with(participant)

    @staticmethod
    @freeze_time("Fri, 25 Jan 2019 03:00:00 EST")
    @mock.patch('ws.tasks.send_email_to_funds')
    def test_send_tomorrow_itiniraries(send_email_to_funds):
        """ Only trips taking place the next day have itineraries sent out. """
        _yesterday, _today, tomorrow, _two_days_from_now = [
            factories.TripFactory.create(
                trip_date=date(2019, 1, day), info=factories.TripInfoFactory.create()
            )
            for day in [24, 25, 26, 27]
        ]

        tasks.send_sole_itineraries()

        # Emails are only sent for trips going out tomorrow
        send_email_to_funds.assert_called_once_with(tomorrow)

    @freeze_time("Fri, 25 Jan 2019 03:00:00 EST")
    @mock.patch('ws.tasks.send_email_to_funds')
    def test_trips_without_itineraries_omitted(self, send_email_to_funds):
        trips_with_itinerary = [
            factories.TripFactory.create(
                trip_date=date(2019, 1, 26), info=factories.TripInfoFactory.create()
            )
            for i in range(2)
        ]

        # Create one trip without an itinerary, on the same day
        factories.TripFactory.create(trip_date=date(2019, 1, 26), info=None)

        tasks.send_sole_itineraries()

        # Emails were sent for only the trips with an itinerary
        self.assertCountEqual(
            [trip for (trip,), kwargs in send_email_to_funds.call_args_list],
            trips_with_itinerary,
        )

    @staticmethod
    @mock.patch('ws.tasks.cache', wraps=cache)
    @mock.patch('ws.utils.member_sheets.update_discount_sheet')
    @mock.patch('ws.utils.member_sheets.update_participant')
    def test_discount_tasks_share_same_key(
        update_participant, update_discount_sheet, mock_cache
    ):
        """ All tasks modifying the same discount sheet must share a task ID.

        This prevents multiple tasks modifying the Google Sheet at the same time.
        """
        discount = factories.DiscountFactory.create(pk=8675)
        participant = factories.ParticipantFactory.create()
        expected_lock_id = 'update_discount-8675'

        tasks.update_discount_sheet_for_participant(discount.pk, participant.pk)
        mock_cache.add.assert_called_with(expected_lock_id, 'true', 600)

        tasks.update_discount_sheet(discount.pk)
        mock_cache.add.assert_called_with(expected_lock_id, 'true', 600)


class DiscountsWithoutGaKeyTest(TestCase):
    """ Test our handling of discounts which opt out of the Google Sheets flow. """

    def setUp(self):
        self.par = factories.ParticipantFactory.create()
        # Some discounts opt out of the Google Sheets flow
        self.discount = factories.DiscountFactory.create(ga_key='')

    def test_update_sheet_for_participant(self):
        """ If we mistakenly wrote a discount without a Google Sheets key, Celery handles it. """
        # Participants shouldn't be able to opt in to these discounts,
        # but make sure Celery doesn't choke if they do.
        self.par.discounts.add(self.discount)

        with mock.patch.object(member_sheets, 'update_participant') as update_par:
            with mock.patch.object(tasks.logger, 'error') as log_error:
                tasks.update_discount_sheet_for_participant(
                    self.discount.pk, self.par.pk
                )

        log_error.assert_called()
        update_par.assert_not_called()

    def test_update_sheet(self):
        """ Updating just a single sheet is handled if that sheet has no Google Sheets key. """
        with mock.patch.object(member_sheets, 'update_participant') as update_par:
            with mock.patch.object(tasks.logger, 'error') as log_error:
                tasks.update_discount_sheet(self.discount.pk)

        log_error.assert_called()
        update_par.assert_not_called()

    @staticmethod
    def test_update_all():
        """ When updating the sheets for all discounts, we exclude ones without a sheet. """
        # Because this discount has no Google Sheets key, we don't do anything
        with mock.patch.object(tasks.update_discount_sheet, 's') as update_sheet:
            tasks.update_all_discount_sheets()
        update_sheet.assert_not_called()

        # If we add another discount, we can bulk update but will exclude the current one
        other_discount = factories.DiscountFactory.create(ga_key='some-koy')

        with mock.patch.object(tasks.update_discount_sheet, 's') as update_sheet:
            with mock.patch.object(tasks, 'group'):
                tasks.update_all_discount_sheets()
        update_sheet.assert_called_once_with(other_discount.pk)
