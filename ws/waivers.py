import xml.etree.ElementTree as ET  # noqa: N817
from typing import Any, NamedTuple, TypedDict, cast

import requests
from mitoc_const import affiliations

from ws import models, settings

AFFILIATION_MAPPING = {aff.CODE: aff.VALUE for aff in affiliations.ALL}


class LoginAccount(TypedDict):
    name: str
    accountId: str
    baseUrl: str
    isDefault: str
    userName: str
    userId: str
    email: str
    siteDescription: str


class Person(NamedTuple):
    """A human involved in the waiver process.

    Generally, this is the Releasor (primary person signing the waiver).
    If the Releasor is a minor, though, this can be their guardian.
    """

    name: str
    email: str


class InitiatedWaiverResult(NamedTuple):
    # The email address that will be used for signing the waiver
    # This is what links the waiver to a MITOC member
    email: str

    # If given, this URL reflects an "embedded URL"
    # That is, it's a URL which can be loaded to direct a user straight to waiver signing.
    # This can be used when a participant already has verified their email address.
    url: str | None


def get_headers() -> dict[str, str]:
    """Get standard headers to be used with every DocuSign API request."""
    creds = ET.Element('DocuSignCredentials')
    ET.SubElement(creds, 'Username').text = settings.DOCUSIGN_USERNAME
    ET.SubElement(creds, 'Password').text = settings.DOCUSIGN_PASSWORD
    ET.SubElement(creds, 'IntegratorKey').text = settings.DOCUSIGN_INTEGRATOR_KEY
    return {
        'X-DocuSign-Authentication': ET.tostring(creds).decode('utf-8'),
        'Accept': 'application/json',
    }


def get_base_url() -> str:
    """Get the base URL from which API requests must be made.

    DocuSign does not guarantee that this URL remains static, so query
    it every time we intend to use the API.

    The response URL will look like:
    https://na2.docusign.net/restapi/v2/accounts/<numeric_account_id>
    """
    v2_base = settings.DOCUSIGN_API_BASE  # (Demo or production)
    resp = requests.get(
        v2_base + 'login_information', headers=get_headers(), timeout=10
    )

    login_accounts = cast(list[LoginAccount], resp.json()['loginAccounts'])
    assert login_accounts
    return login_accounts[0]['baseUrl']


DocusignTabs = dict[str, list[dict[str, Any]]]


def prefilled_tabs(participant: models.Participant) -> DocusignTabs:
    """Return tabs that are pre-filled for the Releasor role."""
    e_contact = participant.emergency_info.emergency_contact
    docusign_affiliation = AFFILIATION_MAPPING[participant.affiliation]
    return {
        'textTabs': [
            {'tabLabel': 'Phone number', 'value': str(participant.cell_phone)},
            {'tabLabel': "Emergency Contact", 'value': e_contact.name},
            {'tabLabel': "Emergency Contact Relation", 'value': e_contact.relationship},
            {
                'tabLabel': "Emergency Contact's Phone",
                'value': str(e_contact.cell_phone),
            },
        ],
        # Map affiliation to a selectable value in the DocuSign template
        'radioGroupTabs': [
            {
                'groupName': 'Affiliation',
                'radios': [{'value': docusign_affiliation, 'selected': True}],
            }
        ],
    }


class _BaseDocusignRole(TypedDict):
    roleName: str
    name: str
    email: str


class DocusignRole(_BaseDocusignRole, total=False):
    """Some extra information possible on a DocuSign role!"""

    tabs: DocusignTabs
    clientUserId: int  # noqa: N815


def get_roles(
    releasor: Person,
    participant: models.Participant | None = None,
    guardian: Person | None = None,
) -> list[DocusignRole]:
    """Return the role definitions, with pre-filled data if available.

    When we create the envelope, the waiver will be sent to the releasor (and a
    guardian, if one is given).
    """
    if participant:
        assert releasor.name == participant.name
        assert releasor.email == participant.email

    releasor_dict: DocusignRole = {
        'roleName': 'Releasor',
        'name': releasor.name,
        'email': releasor.email,
    }
    desk: DocusignRole = {
        'roleName': 'MITOC Desk',
        'name': 'MITOC Desk',
        'email': 'mitocdesk@gmail.com',
    }

    # If there's a participant, copy over medical info & such to prefill form
    if participant:
        releasor_dict['tabs'] = prefilled_tabs(participant)

    if not guardian:
        return [releasor_dict, desk]

    guardian_dict: DocusignRole = {
        'roleName': 'Parent or Guardian',
        'name': guardian.name,
        'email': guardian.email,
    }
    return [releasor_dict, guardian_dict, desk]


def _sign_embedded(
    participant: models.Participant,
    releasor_dict: DocusignRole,
    envelope_id: str,
    base_url: str | None = None,
) -> str:
    """Take a known user and go straight to the waiver flow.

    Normally, we would rely on a waiver being sent to a user's email address
    in order to know that they own the email address. However, in this case,
    we already know that the participant owns the email address, so we can
    go straight into the waiver flow.

    The releasor object is a standard role definition that has already been
    configured for use with a template, and has a 'clientUserId' assigned.
    """
    base_url = base_url or get_base_url()
    recipient_url = f'{base_url}/envelopes/{envelope_id}/views/recipient'
    user = {
        'userName': releasor_dict['name'],
        'email': releasor_dict['email'],
        'clientUserId': releasor_dict['clientUserId'],
        'authenticationMethod': 'email',
        'returnUrl': 'https://mitoc-trips.mit.edu',
    }
    # Fetch a URL that can be used to sign the waiver (expires in 5 minutes)
    redir_url = requests.post(
        recipient_url, json=user, headers=get_headers(), timeout=10
    )
    return cast(str, redir_url.json()['url'])


def initiate_waiver(
    participant: models.Participant | None,
    releasor: Person | None,
    guardian: Person | None,
) -> InitiatedWaiverResult:
    """Create a waiver & send it to the participant (releasor).

    If the participant does not exist (i.e. somebody who's just signing with
    their name and email address), do not attempt to pre-fill the form.

    Returns the email address of the releasor, and an optional URL for
    embedded signing redirection (if None, callers should take no action).
    """
    if participant and releasor:
        assert releasor.name == participant.name
        assert releasor.email == participant.email
    elif participant:
        releasor = Person(name=participant.name, email=participant.email)

    if not releasor:
        raise ValueError("Participant or name/email required!")

    roles = get_roles(releasor, participant, guardian)
    releasor_dict = roles[0]

    # Create a new envelope. By default, this results in an email to each role
    new_env = {
        'status': 'sent',
        'templateId': settings.DOCUSIGN_WAIVER_TEMPLATE_ID,
        'templateRoles': roles,
        'eventNotification': settings.DOCUSIGN_EVENT_NOTIFICATION,
    }

    # If their email is already known to us & authenticated, sign right away
    # (to do embedded signing, we must define user ID at envelope creation)
    if participant:
        releasor_dict['clientUserId'] = participant.pk

    base_url = get_base_url()
    env = requests.post(
        f'{base_url}/envelopes', json=new_env, headers=get_headers(), timeout=10
    )

    # If there's no participant, an email will be sent; no need to redirect
    redir_url: str | None = None

    if participant:  # We need a participant to do embedded signing
        envelope_id = env.json()['envelopeId']
        redir_url = _sign_embedded(participant, releasor_dict, envelope_id, base_url)

    return InitiatedWaiverResult(email=releasor_dict['email'], url=redir_url)
