import contextlib
import unittest
import uuid
from unittest import mock

import requests
from django.test import TestCase
from mitoc_const import affiliations

from ws import settings, waivers
from ws.tests import factories


class HeaderBaseTest(unittest.TestCase):
    def setUp(self):
        patched = mock.patch.object(waivers, 'settings')
        orig_event_notif = settings.DOCUSIGN_EVENT_NOTIFICATION
        self.mocked_settings = patched.start()

        self.mocked_settings.DOCUSIGN_USERNAME = 'djcain@mit.edu'
        self.mocked_settings.DOCUSIGN_PASSWORD = (
            'sooper-secure-hexish-token'  # noqa: S105
        )
        self.mocked_settings.DOCUSIGN_INTEGRATOR_KEY = 'some-integrator-key'
        self.mocked_settings.DOCUSIGN_WAIVER_TEMPLATE_ID = str(uuid.uuid4())
        self.mocked_settings.DOCUSIGN_EVENT_NOTIFICATION = orig_event_notif

        self.addCleanup(patched.stop)

        self.expected_creds = (
            '<DocuSignCredentials>'
            '<Username>djcain@mit.edu</Username>'
            '<Password>sooper-secure-hexish-token</Password>'
            '<IntegratorKey>some-integrator-key</IntegratorKey>'
            '</DocuSignCredentials>'
        )

    EXPECTED_EVENT_NOTIFICATION = {
        'url': 'https://docusign.mitoc.org/members/waiver',
        'loggingEnabled': 'true',
        'requireAcknowledgment': 'true',
        'useSoapInterface': 'false',
        'includeCertificateWithSoap': 'false',
        'signMessageWithX509Cert': 'true',
        'includeDocuments': 'false',
        'includeCertificateOfCompletion': 'false',
        'includeEnvelopeVoidReason': 'true',
        'includeTimeZone': 'true',
        'includeSenderAccountAsCustomField': 'true',
        'includeDocumentFields': 'true',
        'envelopeEvents': [{'envelopeEventStatusCode': 'completed'}],
        'recipientEvents': [{'recipientEventStatusCode': 'Completed'}],
    }


class DocusignHeadersTests(HeaderBaseTest):
    def test_headers(self):
        """Authentication is provided as an XML object in HTTP headers."""
        self.assertEqual(
            waivers.get_headers(),
            {
                'Accept': 'application/json',
                'X-DocuSign-Authentication': self.expected_creds,
            },
        )

    def test_headers_used_fetching_base_url(self):
        """Authentication is provided as an XML object in HTTP headers."""
        self.mocked_settings.DOCUSIGN_BASE = 'https://demo.docusign.net/restapi/v2/'
        login_info = mock.Mock(spec=requests.Response)
        login_info.json.return_value = {
            'loginAccounts': [
                {
                    'name': 'Massachusetts Institute of Technology',
                    'accountId': '123456',
                    'baseUrl': 'https://demo.docusign.net/restapi/v2/accounts/123456',
                    'isDefault': 'true',
                    'userName': 'MITOC',
                    'userId': '123abcd0-1234-1234-1234-01234567890a',
                    'email': 'djcain@mit.edu',
                    'siteDescription': '',
                }
            ]
        }
        with mock.patch.object(requests, 'get') as requests_get:
            requests_get.return_value = login_info
            base_url = waivers.get_base_url()

        self.assertEqual(
            base_url, 'https://demo.docusign.net/restapi/v2/accounts/123456'
        )


@contextlib.contextmanager
def mock_base_url(url='https://demo.docusign.net/restapi/v2/accounts/123456'):
    with mock.patch.object(waivers, 'get_base_url') as get_base_url:
        get_base_url.return_value = url
        yield


class BasicWaiverTests(HeaderBaseTest):
    def test_must_provide_participant_or_releasor(self):
        """We need a name & and an email address somehow to complete a waiver."""
        with self.assertRaises(ValueError):
            waivers.initiate_waiver(participant=None, releasor=None, guardian=None)

    def test_prefilled_tabs(self):
        """When a participant is given, we can prefill information.

        See the `mitoc-waiver` repository for the schema used here.
        """
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

    @mock_base_url()
    def test_initiate_waiver_from_name_email(self):
        with mock.patch.object(requests, 'post') as requests_post:
            result = waivers.initiate_waiver(
                participant=None,
                releasor=waivers.Person(name='Tim Beaver', email='tim@mit.edu'),
                guardian=None,
            )
        requests_post.assert_called_once()
        kwargs = requests_post.call_args[1]
        self.assertEqual(
            kwargs['json'],
            {
                'status': 'sent',
                'templateId': self.mocked_settings.DOCUSIGN_WAIVER_TEMPLATE_ID,
                'templateRoles': [
                    {
                        'roleName': 'Releasor',
                        'name': 'Tim Beaver',
                        'email': 'tim@mit.edu',
                    },
                    {
                        'roleName': 'MITOC Desk',
                        'name': 'MITOC Desk',
                        'email': 'mitocdesk@gmail.com',
                    },
                ],
                'eventNotification': self.EXPECTED_EVENT_NOTIFICATION,
            },
        )

        self.assertEqual(
            result, waivers.InitiatedWaiverResult(email='tim@mit.edu', url=None)
        )


class ParticipantWaiverTests(HeaderBaseTest, TestCase):
    @staticmethod
    @contextlib.contextmanager
    def _mock_posts():
        def fake_post(url, **kwargs):
            resp = mock.Mock(spec=requests.Response)
            if url.endswith('envelopes'):
                resp.json.return_value = {'envelopeId': 'some-envelope-id'}
                return resp

            if url.endswith('views/recipient'):
                resp.json.return_value = {
                    'url': 'https://na2.docusign.net/Signing/StartInSession.aspx?code=long-code-with-encoded-data&persistent_auth_token=no_client_token'
                }
                return resp

            raise ValueError(f"unexpected url {url}")  # pragma: no cover

        with mock.patch.object(requests, 'post') as requests_post:
            requests_post.side_effect = fake_post
            yield requests_post

    @mock_base_url()
    def test_no_guardian(self):
        """When a participant submits the form, we start an embedded flow for them."""
        participant = factories.ParticipantFactory.create(
            name='Tim Beaver', email='tim@mit.edu'
        )

        with self._mock_posts() as requests_post:
            waivers.initiate_waiver(participant, releasor=None, guardian=None)

        self.assertEqual(len(requests_post.call_args_list), 2)

        # The first call is to create a new waiver ("envelope")
        env_args, env_kwargs = requests_post.call_args_list[0]
        self.assertEqual(
            env_args,
            ('https://demo.docusign.net/restapi/v2/accounts/123456/envelopes',),
        )
        self.assertEqual(
            env_kwargs['headers'],
            {
                'Accept': 'application/json',
                'X-DocuSign-Authentication': self.expected_creds,
            },
        )

        self.assertEqual(
            env_kwargs['json'],
            {
                'status': 'sent',
                'templateId': self.mocked_settings.DOCUSIGN_WAIVER_TEMPLATE_ID,
                'templateRoles': [
                    {
                        'roleName': 'Releasor',
                        'name': 'Tim Beaver',
                        'email': 'tim@mit.edu',
                        'clientUserId': participant.pk,
                        'tabs': waivers.prefilled_tabs(participant),  # Tested earlier
                    },
                    {
                        'roleName': 'MITOC Desk',
                        'name': 'MITOC Desk',
                        'email': 'mitocdesk@gmail.com',
                    },
                ],
                'eventNotification': self.EXPECTED_EVENT_NOTIFICATION,
            },
        )

        # The second call is to get a URL for the waiver
        embedded_args, embedded_kwargs = requests_post.call_args_list[1]
        self.assertEqual(
            embedded_args,
            (
                'https://demo.docusign.net/restapi/v2/accounts/123456/envelopes/some-envelope-id/views/recipient',
            ),
        )

        self.assertEqual(
            embedded_kwargs['headers'],
            {
                'Accept': 'application/json',
                'X-DocuSign-Authentication': self.expected_creds,
            },
        )
        self.assertEqual(
            embedded_kwargs['json'],
            {
                'userName': 'Tim Beaver',
                'email': 'tim@mit.edu',
                'clientUserId': participant.pk,
                'authenticationMethod': 'email',
                'returnUrl': 'https://mitoc-trips.mit.edu',
            },
        )

    @mock_base_url()
    def test_guardian(self):
        participant = factories.ParticipantFactory.create(
            name='Tim Beaver', email='tim@mit.edu'
        )

        with self._mock_posts() as requests_post:
            waivers.initiate_waiver(
                participant,
                # Specifying releasor is redundant, but allowed
                releasor=waivers.Person(name='Tim Beaver', email='tim@mit.edu'),
                guardian=waivers.Person(
                    name='Timothy Beaver, Sr', email='tim@alum.mit.edu'
                ),
            )

        self.assertEqual(len(requests_post.call_args_list), 2)

        # The first call is to create a new waiver ("envelope")
        env_args, env_kwargs = requests_post.call_args_list[0]
        self.assertEqual(
            env_args,
            ('https://demo.docusign.net/restapi/v2/accounts/123456/envelopes',),
        )

        self.assertEqual(
            env_kwargs['json'],
            {
                'status': 'sent',
                'templateId': self.mocked_settings.DOCUSIGN_WAIVER_TEMPLATE_ID,
                'templateRoles': [
                    {
                        'roleName': 'Releasor',
                        'name': 'Tim Beaver',
                        'email': 'tim@mit.edu',
                        'clientUserId': participant.pk,
                        'tabs': waivers.prefilled_tabs(participant),  # Tested earlier
                    },
                    {
                        'roleName': 'Parent or Guardian',
                        'name': 'Timothy Beaver, Sr',
                        'email': 'tim@alum.mit.edu',
                    },
                    {
                        'roleName': 'MITOC Desk',
                        'name': 'MITOC Desk',
                        'email': 'mitocdesk@gmail.com',
                    },
                ],
                'eventNotification': self.EXPECTED_EVENT_NOTIFICATION,
            },
        )

        # The second call is to get a URL for the waiver
        embedded_args, embedded_kwargs = requests_post.call_args_list[1]
        self.assertEqual(
            embedded_args,
            (
                'https://demo.docusign.net/restapi/v2/accounts/123456/envelopes/some-envelope-id/views/recipient',
            ),
        )

        # The participant must sign first, then the guardian can
        self.assertEqual(
            embedded_kwargs['json'],
            {
                'userName': 'Tim Beaver',
                'email': 'tim@mit.edu',
                'clientUserId': participant.pk,
                'authenticationMethod': 'email',
                'returnUrl': 'https://mitoc-trips.mit.edu',
            },
        )
