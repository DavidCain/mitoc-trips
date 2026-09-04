import contextlib
import time
import uuid
from collections.abc import Iterator

import jwt
import responses
from django.test import SimpleTestCase
from mitoc_const import affiliations
from responses import matchers

from ws import waivers
from ws.tests import factories

# This is the RSA-2048 test key from https://www.rfc-editor.org/info/rfc9500/#section-2
TEST_RSA_KEY = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAsPnoGUOnrpiSqt4XynxA+HRP7S+BSObI6qJ7fQAVSPtRkqso
tWxQYLEYzNEx5ZSHTGypibVsJylvCfuToDTfMul8b/CZjP2Ob0LdpYrNH6l5hvFE
89FU1nZQF15oVLOpUgA7wGiHuEVawrGfey92UE68mOyUVXGweJIVDdxqdMoPvNNU
l86BU02vlBiESxOuox+dWmuVV7vfYZ79Toh/LUK43YvJh+rhv4nKuF7iHjVjBd9s
B6iDjj70HFldzOQ9r8SRI+9NirupPTkF5AKNe6kUhKJ1luB7S27ZkvB3tSTT3P59
3VVJvnzOjaA1z6Cz+4+eRvcysqhrRgFlwI9TEwIDAQABAoIBAEEYiyDP29vCzx/+
dS3LqnI5BjUuJhXUnc6AWX/PCgVAO+8A+gZRgvct7PtZb0sM6P9ZcLrweomlGezI
FrL0/6xQaa8bBr/ve/a8155OgcjFo6fZEw3Dz7ra5fbSiPmu4/b/kvrg+Br1l77J
aun6uUAs1f5B9wW+vbR7tzbT/mxaUeDiBzKpe15GwcvbJtdIVMa2YErtRjc1/5B2
BGVXyvlJv0SIlcIEMsHgnAFOp1ZgQ08aDzvilLq8XVMOahAhP1O2A3X8hKdXPyrx
IVWE9bS9ptTo+eF6eNl+d7htpKGEZHUxinoQpWEBTv+iOoHsVunkEJ3vjLP3lyI/
fY0NQ1ECgYEA3RBXAjgvIys2gfU3keImF8e/TprLge1I2vbWmV2j6rZCg5r/AS0u
pii5CvJ5/T5vfJPNgPBy8B/yRDs+6PJO1GmnlhOkG9JAIPkv0RBZvR0PMBtbp6nT
Y3yo1lwamBVBfY6rc0sLTzosZh2aGoLzrHNMQFMGaauORzBFpY5lU50CgYEAzPHl
u5DI6Xgep1vr8QvCUuEesCOgJg8Yh1UqVoY/SmQh6MYAv1I9bLGwrb3WW/7kqIoD
fj0aQV5buVZI2loMomtU9KY5SFIsPV+JuUpy7/+VE01ZQM5FdY8wiYCQiVZYju9X
Wz5LxMNoz+gT7pwlLCsC4N+R8aoBk404aF1gum8CgYAJ7VTq7Zj4TFV7Soa/T1eE
k9y8a+kdoYk3BASpCHJ29M5R2KEA7YV9wrBklHTz8VzSTFTbKHEQ5W5csAhoL5Fo
qoHzFFi3Qx7MHESQb9qHyolHEMNx6QdsHUn7rlEnaTTyrXh3ifQtD6C0yTmFXUIS
CW9wKApOrnyKJ9nI0HcuZQKBgQCMtoV6e9VGX4AEfpuHvAAnMYQFgeBiYTkBKltQ
XwozhH63uMMomUmtSG87Sz1TmrXadjAhy8gsG6I0pWaN7QgBuFnzQ/HOkwTm+qKw
AsrZt4zeXNwsH7QXHEJCFnCmqw9QzEoZTrNtHJHpNboBuVnYcoueZEJrP8OnUG3r
UjmopwKBgAqB2KYYMUqAOvYcBnEfLDmyZv9BTVNHbR2lKkMYqv5LlvDaBxVfilE0
2riO4p6BaAdvzXjKeRrGNEKoHNBpOSfYCOM16NjL8hIZB1CaV3WbT5oY+jp7Mzd5
7d56RZOE+ERK2uz/7JX9VSsM/LbH9pJibd4e8mikDS9ntciqOH/3
-----END RSA PRIVATE KEY-----
"""


EXPECTED_EVENT_NOTIFICATION = {
    "url": "https://docusign.mitoc.org/members/waiver",
    "loggingEnabled": "true",
    "requireAcknowledgment": "true",
    "useSoapInterface": "false",
    "includeCertificateWithSoap": "false",
    "signMessageWithX509Cert": "true",
    "includeHMAC": "true",
    "includeDocuments": "false",
    "includeCertificateOfCompletion": "false",
    "includeEnvelopeVoidReason": "true",
    "includeTimeZone": "true",
    "includeSenderAccountAsCustomField": "true",
    "includeDocumentFields": "true",
    "envelopeEvents": [{"envelopeEventStatusCode": "completed"}],
    "recipientEvents": [{"recipientEventStatusCode": "Completed"}],
}


class WaiverBaseTest(SimpleTestCase):
    def setUp(self) -> None:
        self.addCleanup(
            waivers._get_possibly_cached_access_token.cache_clear  # noqa: SLF001
        )

    @contextlib.contextmanager
    def jwt_access_token(
        self, **docusign_settings: str
    ) -> Iterator[responses.RequestsMock]:
        django_settings = {
            # These are required at minimum, others can be overridden
            "DOCUSIGN_ACCOUNT_HOST": "account-d.docusign.com",
            "DOCUSIGN_INTEGRATOR_KEY": str(uuid.uuid4()),
            "DOCUSIGN_API_USER_GUID": str(uuid.uuid4()),
            "DOCUSIGN_RSA_PRIVATE_KEY": TEST_RSA_KEY,
            **docusign_settings,
        }
        fake_access_token = jwt.encode(
            {"exp": time.time() + 3600},
            key="in practice this will actually be signed using RS256 and not HMAC",
        )
        with responses.RequestsMock() as rsps:
            rsps.post(
                url="https://account-d.docusign.com/oauth/token",
                json={"access_token": fake_access_token},
            )
            with self.settings(**django_settings):
                headers = waivers.get_headers()
                yield rsps

            self.assertEqual(
                headers,
                {
                    "Authorization": "Bearer " + fake_access_token,
                    "Accept": "application/json",
                },
            )


class BasicWaiverTests(WaiverBaseTest):
    @responses.activate  # (no API calls)
    def test_must_provide_participant_or_releasor(self) -> None:
        """We need a name & and an email address somehow to complete a waiver."""
        with self.assertRaises(ValueError) as cm:
            waivers.initiate_waiver(participant=None, releasor=None, guardian=None)
        self.assertEqual(str(cm.exception), "Participant or name/email required!")

    def test_prefilled_tabs(self) -> None:
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
            "textTabs": [
                {"tabLabel": "Phone number", "value": "+17815551234"},
                {"tabLabel": "Emergency Contact", "value": "Beatrice Beaver"},
                {"tabLabel": "Emergency Contact Relation", "value": "Mother"},
                {"tabLabel": "Emergency Contact's Phone", "value": "+17815550342"},
            ],
            "radioGroupTabs": [
                {
                    "groupName": "Affiliation",
                    "radios": [{"value": "Non-affiliate", "selected": True}],
                }
            ],
        }

        self.assertEqual(waivers.prefilled_tabs(participant), expected)

    @responses.activate
    def test_initiate_waiver_from_name_email(self) -> None:
        expected_payload = {
            "status": "sent",
            "templateId": "some template UUID",
            "templateRoles": [
                {
                    "roleName": "Releasor",
                    "name": "Tim Beaver",
                    "email": "tim@mit.edu",
                },
                {
                    "roleName": "MITOC Desk",
                    "name": "MITOC Desk",
                    "email": "mitocdesk@gmail.com",
                },
            ],
            "eventNotification": EXPECTED_EVENT_NOTIFICATION,
        }
        with self.jwt_access_token(
            DOCUSIGN_API_USER_GUID="uuid-from-the-docusign-apps-and-keys-page",
            DOCUSIGN_WAIVER_TEMPLATE_ID="some template UUID",
        ) as rsps:
            rsps.post(
                "https://demo.docusign.net/restapi/v2.1/accounts/uuid-from-the-docusign-apps-and-keys-page/envelopes",
                match=[matchers.json_params_matcher(expected_payload)],
            )
            result = waivers.initiate_waiver(
                participant=None,
                releasor=waivers.Person(name="Tim Beaver", email="tim@mit.edu"),
                guardian=None,
            )

        self.assertEqual(
            result, waivers.InitiatedWaiverResult(email="tim@mit.edu", url=None)
        )


class ParticipantWaiverTests(WaiverBaseTest):
    def test_no_guardian(self) -> None:
        """When a participant submits the form, we start an embedded flow for them."""
        participant = factories.ParticipantFactory.build(
            name="Tim Beaver", email="tim@mit.edu"
        )

        expected_envelope_payload = {
            "status": "sent",
            "templateId": "some template UUID",
            "templateRoles": [
                {
                    "roleName": "Releasor",
                    "name": "Tim Beaver",
                    "email": "tim@mit.edu",
                    "clientUserId": participant.pk,
                    "tabs": waivers.prefilled_tabs(participant),  # Tested earlier
                },
                {
                    "roleName": "MITOC Desk",
                    "name": "MITOC Desk",
                    "email": "mitocdesk@gmail.com",
                },
            ],
            "eventNotification": EXPECTED_EVENT_NOTIFICATION,
        }
        expected_embedded_payload = {
            "userName": "Tim Beaver",
            "email": "tim@mit.edu",
            "clientUserId": participant.pk,
            "authenticationMethod": "email",
            "returnUrl": "https://mitoc-trips.mit.edu",
        }

        with self.jwt_access_token(
            DOCUSIGN_API_USER_GUID="uuid-from-the-docusign-apps-and-keys-page",
            DOCUSIGN_WAIVER_TEMPLATE_ID="some template UUID",
        ) as rsps:
            rsps.post(
                "https://demo.docusign.net/restapi/v2.1/accounts/uuid-from-the-docusign-apps-and-keys-page/envelopes",
                match=[matchers.json_params_matcher(expected_envelope_payload)],
                json={"envelopeId": "some-envelope-id"},
            )
            rsps.post(
                "https://demo.docusign.net/restapi/v2.1/accounts/uuid-from-the-docusign-apps-and-keys-page/envelopes/some-envelope-id/views/recipient",
                match=[matchers.json_params_matcher(expected_embedded_payload)],
                json={"url": "https://docusign.com/some/url"},
            )
            result = waivers.initiate_waiver(participant, releasor=None, guardian=None)
        self.assertEqual(result.email, "tim@mit.edu")
        self.assertEqual(result.url, "https://docusign.com/some/url")

    def test_guardian(self) -> None:
        participant = factories.ParticipantFactory.build(
            name="Tim Beaver", email="tim@mit.edu"
        )
        expected_envelope_payload = {
            "status": "sent",
            "templateId": "some template UUID",
            "templateRoles": [
                {
                    "roleName": "Releasor",
                    "name": "Tim Beaver",
                    "email": "tim@mit.edu",
                    "clientUserId": participant.pk,
                    "tabs": waivers.prefilled_tabs(participant),  # Tested earlier
                },
                {
                    "roleName": "Parent or Guardian",
                    "name": "Timothy Beaver, Sr",
                    "email": "tim@alum.mit.edu",
                },
                {
                    "roleName": "MITOC Desk",
                    "name": "MITOC Desk",
                    "email": "mitocdesk@gmail.com",
                },
            ],
            "eventNotification": EXPECTED_EVENT_NOTIFICATION,
        }

        expected_embedded_payload = {
            "userName": "Tim Beaver",
            "email": "tim@mit.edu",
            "clientUserId": participant.pk,
            "authenticationMethod": "email",
            "returnUrl": "https://mitoc-trips.mit.edu",
        }

        with self.jwt_access_token(
            DOCUSIGN_API_USER_GUID="uuid-from-the-docusign-apps-and-keys-page",
            DOCUSIGN_WAIVER_TEMPLATE_ID="some template UUID",
        ) as rsps:
            rsps.post(
                "https://demo.docusign.net/restapi/v2.1/accounts/uuid-from-the-docusign-apps-and-keys-page/envelopes",
                match=[matchers.json_params_matcher(expected_envelope_payload)],
                json={"envelopeId": "some-envelope-id"},
            )
            rsps.post(
                "https://demo.docusign.net/restapi/v2.1/accounts/uuid-from-the-docusign-apps-and-keys-page/envelopes/some-envelope-id/views/recipient",
                match=[matchers.json_params_matcher(expected_embedded_payload)],
                json={"url": "https://docusign.com/some/url"},
            )
            result = waivers.initiate_waiver(
                participant,
                # Specifying releasor is redundant, but allowed
                releasor=waivers.Person(name="Tim Beaver", email="tim@mit.edu"),
                guardian=waivers.Person(
                    name="Timothy Beaver, Sr", email="tim@alum.mit.edu"
                ),
            )
