from collections import OrderedDict
from unittest import mock

from ws.privacy import DataDump
from ws.tests import TestCase, factories


class DataDumpTest(TestCase):
    def test_minimal_participant(self):
        participant = factories.ParticipantFactory.create()
        data = DataDump(participant.pk)

        self.assertEqual(
            data.all_data,
            OrderedDict(
                [
                    (
                        'user',
                        {
                            'last_login': None,
                            'date_joined': mock.ANY,
                            'name': 'Test Participant',
                            'profile_last_updated': mock.ANY,
                            'cell_phone': '',
                            'affiliation': 'Non-affiliate',
                            'emails': [
                                {
                                    'email': participant.email,
                                    'verified': True,
                                    'primary': True,
                                }
                            ],
                        },
                    ),
                    ('membership', None),
                    ('discounts', []),
                    ('car', None),
                    (
                        'medical',
                        {
                            'emergency_contact': {
                                'name': 'My Mother',
                                'cell_phone': '+17815550342',
                                'relationship': 'Mother',
                                'email': 'mum@example.com',
                            },
                            'allergies': 'None',
                            'medications': 'None',
                            'medical_history': 'None',
                        },
                    ),
                    ('lottery_info', None),
                    ('leader_ratings', {}),
                    ('leader_applications', {}),
                    ('winter_school_lecture_attendance', []),
                    ('trips', {'wimped': [], 'led': [], 'created': []}),
                    ('signups', []),
                    ('feedback', {'received': [], 'given': []}),
                ]
            ),
        )

    def test_success(self):
        """ Create a bunch of data about the participant, ensure that dumping it works. """
        participant = factories.ParticipantFactory.create()
        participant.discounts.add(factories.DiscountFactory.create())
        participant.car = factories.CarFactory.create()
        participant.save()
        factories.LeaderRatingFactory.create(participant=participant)
        factories.LeaderRatingFactory.create(creator=participant)
        factories.LotteryInfoFactory.create(participant=participant)

        factories.TripFactory.create(creator=participant, name="First trip")
        factories.TripFactory.create(creator=participant, name="Second trip")
        factories.FeedbackFactory.create(leader=participant)
        factories.FeedbackFactory.create(participant=participant)

        factories.SignUpFactory.create(on_trip=True, participant=participant)
        factories.SignUpFactory.create(on_trip=False, participant=participant)
        factories.SignUpFactory.create(on_trip=False, participant=participant)
        factories.ClimbingLeaderApplicationFactory.create(participant=participant)

        data = DataDump(participant.pk)
        results = data.all_data
        self.assertTrue(isinstance(results, OrderedDict))
        # (Won't actually inspect the results of this, since fixture defaults will likely change)
        # Just ensure that they're actually filled.
        self.assertTrue(results['feedback']['received'])
        self.assertTrue(results['feedback']['given'])
        self.assertTrue(results['lottery_info'])
        self.assertTrue(results['leader_ratings'])
        self.assertTrue(results['leader_applications'])
        self.assertTrue(results['signups'])
