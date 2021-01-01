import json
from datetime import date
from unittest import mock

import dateutil.parser
from freezegun import freeze_time
from mitoc_const import affiliations

from ws import enums, models, tasks
from ws.tests import TestCase, factories


class PostHelper:
    def _post(self, json_data):
        return self.client.post(
            '/preferences/lottery/', json_data, content_type='application/json',
        )


class LotteryPreferencesDriverStatusTests(TestCase, PostHelper):
    # This dictionary doubles as both:
    # 1. All the valid arguments to CarForm except `participant`
    # 2. A valid form to be submitted in POST
    TEST_CAR_INFO = {
        'license_plate': '559DKP',
        'state': 'MA',
        'make': 'Honda',
        'model': 'Accord',
        'year': 2001,
        'color': 'Purple',
    }

    def test_bad_lottery_form(self):
        """ The lottery form must have all its keys specified. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)
        self.assertEqual(self._post({}).status_code, 400)
        self.assertEqual(self._post({'signups': []}).status_code, 400)

    def test_bad_car_form(self):
        """ For car owners, the form must specify vehicle information. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)

        # If specifying that you own a car you're willing to drive, you *must* give info
        response = self._post(
            {'signups': [], 'number_of_passengers': 4, 'car_status': 'own'}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'message': 'Car form invalid'})

        # All fields on CarForm are required
        self.assertEqual(
            self._post(
                {
                    'signups': [],
                    'car_status': 'own',
                    'number_of_passengers': 4,
                    'license_plate': '123ABC',
                }
            ).status_code,
            400,
        )

    @freeze_time("2019-01-15 12:25:00 EST")
    def test_no_car_no_trips_no_pairing(self):
        """ Test the simplest submission of a user with no real preferences to express. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        self.client.force_login(par.user)
        response = self._post({'signups': [], 'car_status': 'none'},)

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, 'none')
        self.assertIsNone(par.lotteryinfo.number_of_passengers)
        self.assertIsNone(par.lotteryinfo.paired_with)
        self.assertEqual(
            par.lotteryinfo.last_updated,
            dateutil.parser.isoparse("2019-01-15T12:25:00-05:00"),
        )

    def test_can_drive_current_car(self):
        """ If a participant has a car on file, we default to using that car. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        car = models.Car(participant=par, **self.TEST_CAR_INFO)
        car.save()
        par.car = car
        par.save()

        self.client.force_login(par.user)
        response = self.client.get('/preferences/lottery/')
        self.assertEqual(response.status_code, 200)
        # The car is given in the context to pre-fill the form
        self.assertEqual(response.context['car_form'].instance, par.car)
        # However, the user isn't defaulted to offering to drive.
        # They must explicitly consent to do so
        self.assertEqual(response.context['lottery_form'].initial, {})

    @freeze_time("2019-01-15 12:25:00 EST")
    def test_can_drive_new_car(self):
        """ Participants who own a car can express their willingness to drive.

        They can also give their car's information straight from the form, even
        if they hadn't previously given any info.
        """
        par = factories.ParticipantFactory.create(lotteryinfo=None, car=None)

        self.client.force_login(par.user)
        response = self._post(
            {
                'signups': [],
                'car_status': 'own',
                'number_of_passengers': 4,
                # These fields all correspond to CarForm
                # (In the future, we should probably use a form prefix)
                **self.TEST_CAR_INFO,
            },
        )

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, 'own')
        self.assertEqual(par.lotteryinfo.number_of_passengers, 4)

        # We created a new car entry for the participant.
        self.assertEqual(
            par.car, models.Car(id=par.car.id, **self.TEST_CAR_INFO),
        )
        self.assertEqual(
            par.lotteryinfo.last_updated,
            dateutil.parser.isoparse("2019-01-15T12:25:00-05:00"),
        )

        # Participant still isn't paired with anybody
        self.assertIsNone(par.lotteryinfo.paired_with)

    def test_willing_to_rent(self):
        """ Participants can express a willingness to rent. """
        par = factories.ParticipantFactory.create(lotteryinfo=None, car=None)

        self.client.force_login(par.user)
        response = self._post(
            {'signups': [], 'car_status': 'rent', 'number_of_passengers': 3},
        )

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, 'rent')
        self.assertEqual(par.lotteryinfo.number_of_passengers, 3)
        self.assertIsNone(par.car)

    def test_willing_to_rent_unknown_seats(self):
        """ It's valid to not know how many passengers your car would seat.

        It makes sense that if you're willing to rent, you can't know in
        advance how many people a hypothetical car would seat.
        """
        par = factories.ParticipantFactory.create(lotteryinfo=None, car=None)

        self.client.force_login(par.user)
        response = self._post(
            {'signups': [], 'car_status': 'rent', 'number_of_passengers': None},
        )

        self.assertEqual(response.status_code, 200)

        par.refresh_from_db()
        self.assertEqual(par.lotteryinfo.car_status, 'rent')
        self.assertIsNone(par.lotteryinfo.number_of_passengers)
        self.assertIsNone(par.car)


@freeze_time("2019-01-08 12:25:00 EST")
class LotteryPreferencesSignupTests(TestCase, PostHelper):
    def test_missing_ordering(self):
        """ Signups must specify signup ID, deletion, and ordering. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)

        signup = factories.SignUpFactory.create(
            participant=par,
            trip__algorithm='lottery',
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        response = self._post(
            {
                'signups': [
                    # No ordering given
                    {'id': signup.pk, 'deleted': False},
                ],
                'car_status': 'none',
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'message': 'Unable to save signups'})

    def test_invalid_ordering(self):
        """ Ordering must be null or numeric. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)
        self.client.force_login(par.user)

        signup = factories.SignUpFactory.create(
            participant=par,
            trip__algorithm='lottery',
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        response = self._post(
            {
                'signups': [{'id': signup.pk, 'deleted': False, 'order': 'threeve'},],
                'car_status': 'none',
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'message': 'Unable to save signups'})

    def test_default_ranking(self):
        """ By default, we list ranked signups by time of creation. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        okay, fave, hate = [
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm='lottery',
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
                trip__name=name,
            )
            for name in ['So-so', 'Amazing', 'Blech']
        ]

        # Signups for other types of trips are excluded; only upcoming WS trips
        factories.SignUpFactory.create(
            participant=par,
            trip__algorithm='lottery',
            trip__program=enums.Program.HIKING.value,
            trip__trip_date=date(2019, 3, 12),
        )
        factories.SignUpFactory.create(
            participant=par,
            trip__algorithm='lottery',
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 7),
        )
        # Of course, another participant's signups aren't counted
        factories.SignUpFactory.create(
            trip__algorithm='lottery',
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        self.client.force_login(par.user)
        # We initially order signups by time of creation
        response = self.client.get('/preferences/lottery/')
        self.assertEqual(response.status_code, 200)
        expected = [
            {'id': okay.pk, 'trip': {'id': okay.trip.pk, 'name': 'So-so'}},
            {'id': fave.pk, 'trip': {'id': fave.trip.pk, 'name': 'Amazing'}},
            {'id': hate.pk, 'trip': {'id': hate.trip.pk, 'name': 'Blech'}},
        ]
        self.assertEqual(response.context['ranked_signups'], json.dumps(expected))

    def test_delete_signups(self):
        """ We allow participants to remove signups. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        keep, kill = [
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm='lottery',
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
                trip__name=name,
            )
            for name in ['Great trip', 'Bad trip']
        ]

        self.client.force_login(par.user)
        response = self._post(
            {
                'signups': [
                    {'id': keep.pk, 'deleted': False, 'order': 1},
                    {'id': kill.pk, 'deleted': True, 'order': None},
                ],
                'car_status': 'none',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(models.SignUp.objects.filter(pk=kill.pk).exists())

    def test_rank_signups(self):
        """ Participants may manually rank their signups in order of preference. """
        par = factories.ParticipantFactory.create(lotteryinfo=None)

        okay, fave, hate = [
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm='lottery',
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
                trip__name=name,
            )
            for name in ['So-so', 'Amazing', 'Blech']
        ]

        self.client.force_login(par.user)
        response = self._post(
            {
                'signups': [
                    {'id': hate.pk, 'deleted': False, 'order': 3},
                    {'id': fave.pk, 'deleted': False, 'order': 1},
                    {'id': okay.pk, 'deleted': False, 'order': 2},
                ],
                'car_status': 'none',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [s.pk for s in par.signup_set.order_by('order')],
            [fave.pk, okay.pk, hate.pk],
        )

    def test_cannot_delete_others_signups(self):
        """ For obvious reasons, participants should not be allowed to remove others' signups. """
        attacker = factories.ParticipantFactory.create()
        victim = factories.ParticipantFactory.create()

        other_signup = factories.SignUpFactory.create(
            participant=victim,
            trip__algorithm='lottery',
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date=date(2019, 1, 12),
        )

        self.client.force_login(attacker.user)
        response = self._post(
            {
                'signups': [{'id': other_signup.pk, 'deleted': True, 'order': 1}],
                'car_status': 'none',
            }
        )
        # We give a 200, even though we could possibly return a 403
        self.assertEqual(response.status_code, 200)
        self.assertTrue(models.SignUp.objects.filter(pk=other_signup.pk).exists())

    def test_can_only_delete_ws_lottery_signups(self):
        """ This route must not provide an undocumented means to drop off trips.

        Deletion of signups should *only* be for signups where the user is not on
        the trip because it's in the lottery stage of a Winter School trip.
        """
        par = factories.ParticipantFactory.create()
        not_deletable = [
            factories.SignUpFactory.create(
                participant=par,
                trip__algorithm='fcfs',
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
            ),
            # An edge case, but it's technically possible to be pre-placed on a lottery trip
            factories.SignUpFactory.create(
                on_trip=True,
                participant=par,
                trip__algorithm='lottery',
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date=date(2019, 1, 12),
            ),
        ]
        self.client.force_login(par.user)
        response = self._post(
            {
                'signups': [
                    {'id': signup.pk, 'deleted': True, 'order': None}
                    for signup in not_deletable
                ],
                'car_status': 'none',
            }
        )
        # None of the specified signups were actually deleted
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            models.SignUp.objects.filter(pk__in=[s.pk for s in not_deletable]).count(),
            len(not_deletable),
        )


class DiscountsTest(TestCase):
    def test_authenticated_users_only(self):
        """ Users must be signed in to enroll in discounts. """
        response = self.client.get('/preferences/discounts/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/accounts/login/?next=/preferences/discounts/')

    def test_users_with_info_only(self):
        """ Participant records are required. """
        user = factories.UserFactory.create()
        self.client.force_login(user)
        response = self.client.get('/preferences/discounts/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/profile/edit/?next=/preferences/discounts/')

    def test_successful_enrollment(self):
        """ Participants can enroll in a selection of discounts. """
        par = factories.ParticipantFactory.create()
        gym = factories.DiscountFactory.create(ga_key='test-key-to-update-sheet')
        # Another discount exists, but they don't enroll in it
        factories.DiscountFactory.create()

        # When showing the page, we exclude the students-only discount
        # If the user tries to bypass the students-only rule, they still cannot enroll
        self.client.force_login(par.user)
        with mock.patch.object(tasks, 'update_discount_sheet_for_participant') as task:
            self.client.post('/preferences/discounts/', {'discounts': str(gym.pk)})
        # Immediately after signup, we sync this user to the sheet
        task.delay.assert_called_once_with(gym.pk, par.pk)

        self.assertEqual([d.pk for d in par.discounts.all()], [gym.pk])

    def test_inactive_discounts_excluded(self):
        """ We don't show inactive discounts to participants. """
        par = factories.ParticipantFactory.create()
        active = factories.DiscountFactory.create(active=True, name='Active Discount')
        factories.DiscountFactory.create(active=False, name='Inactive Discount')

        self.client.force_login(par.user)

        response = self.client.get('/preferences/discounts/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context['form'].fields['discounts'].choices),
            [(active.pk, 'Active Discount')],
        )

    def test_student_only_discounts_excluded(self):
        """ If the participant is not a student, they cannot see student-only discounts. """
        par = factories.ParticipantFactory.create(
            affiliation=affiliations.NON_AFFILIATE.CODE
        )
        student_only = factories.DiscountFactory.create(
            student_required=True, name='Students Only'
        )
        open_discount = factories.DiscountFactory.create(
            student_required=False, name='All members allowed'
        )
        self.client.force_login(par.user)

        # When showing the page, we exclude the students-only discount
        response = self.client.get('/preferences/discounts/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context['form'].fields['discounts'].choices),
            [(open_discount.pk, 'All members allowed')],
        )

        # If the user tries to bypass the students-only rule, they still cannot enroll
        response = self.client.post(
            '/preferences/discounts/',
            {'discounts': [student_only.pk, open_discount.pk]},
        )
        self.assertIn('discounts', response.context['form'].errors)
        self.assertFalse(par.discounts.exists())

        response = self.client.post(
            '/preferences/discounts/', {'discounts': [student_only.pk]},
        )
        self.assertIn('discounts', response.context['form'].errors)
        self.assertFalse(par.discounts.exists())

    def test_students_can_use_student_only_discounts(self):
        """ Students are obviously eligible for student-only discounts. """
        par = factories.ParticipantFactory.create(
            affiliation=affiliations.MIT_UNDERGRAD.CODE
        )
        student_only = factories.DiscountFactory.create(
            student_required=True, name='Students Only'
        )
        open_discount = factories.DiscountFactory.create(
            student_required=False, name='All members allowed'
        )
        self.client.force_login(par.user)

        # When showing the page, we show them both discounts, alphabetically
        response = self.client.get('/preferences/discounts/')
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            list(response.context['form'].fields['discounts'].choices),
            [
                (open_discount.pk, 'All members allowed'),
                (student_only.pk, 'Students Only'),
            ],
        )

        # They can enroll in both
        with mock.patch.object(tasks, 'update_discount_sheet_for_participant') as task:
            response = self.client.post(
                '/preferences/discounts/',
                {'discounts': [student_only.pk, open_discount.pk]},
            )
        task.delay.assert_has_calls(
            [mock.call(student_only.pk, par.pk), mock.call(open_discount.pk, par.pk)]
        )
        self.assertCountEqual(
            [d.pk for d in par.discounts.all()], [student_only.pk, open_discount.pk]
        )

    def test_removal_from_discount(self):
        """ Unenrollment is supported too. """
        par = factories.ParticipantFactory.create()
        discount = factories.DiscountFactory.create()
        par.discounts.add(discount)

        self.client.force_login(par.user)
        with mock.patch.object(tasks, 'update_discount_sheet_for_participant') as task:
            self.client.post('/preferences/discounts/', {'discounts': []})
        # We don't bother updating the sheet, instead relying on the daily removal script
        task.delay.assert_not_called()

        self.assertFalse(par.discounts.exists())
