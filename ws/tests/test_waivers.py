import unittest

from mitoc_const import affiliations

from ws import waivers
from ws.tests import factories


class WaiverTests(unittest.TestCase):
    def test_prefilled_tabs(self):
        participant = factories.ParticipantFactory.build(
            cell_phone="+17815551234",
            affiliation=affiliations.NON_AFFILIATE.CODE,
            emergency_info=factories.EmergencyInfoFactory.build(
                emergency_contact=factories.EmergencyContactFactory.build(
                    name="Beatrice Beaver",
                    cell_phone="+17815550342",
                    relationship="Mother",
                    email="mum@mit.edu",
                )
            ),
        )
        expected = {
            'textTabs': [
                {'tabLabel': 'Phone number', 'value': '+17815551234'},
                {'tabLabel': 'Emergency Contact', 'value': 'Beatrice Beaver'},
                {'tabLabel': 'Emergency Contact Relation', 'value': 'Mother'},
                {'tabLabel': "Emergency Contact's Phone", 'value': '+17815550342'},
            ],
            'radioGroupTabs': [
                {
                    'groupName': 'Affiliation',
                    'radios': [{'value': 'Non-affiliate', 'selected': True}],
                }
            ],
        }

        self.assertEqual(waivers.prefilled_tabs(participant), expected)
