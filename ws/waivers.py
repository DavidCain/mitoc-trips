import xml.etree.cElementTree as ET

import requests

from mitoc_const import affiliations

from ws import settings


AFFILIATION_MAPPING = {aff.CODE: aff.VALUE for aff in affiliations.ALL}

# Deprecated codes ('S' is omitted since we can't map for sure)
AFFILIATION_MAPPING['M'] = affiliations.MIT_AFFILIATE.VALUE
AFFILIATION_MAPPING['N'] = affiliations.NON_AFFILIATE.VALUE


def get_headers():
    """ Get standard headers to be used with every DocuSign API request. """
    creds = ET.Element('DocuSignCredentials')
    ET.SubElement(creds, 'Username').text = settings.DOCUSIGN_USERNAME
    ET.SubElement(creds, 'Password').text = settings.DOCUSIGN_PASSWORD
    ET.SubElement(creds, 'IntegratorKey').text = settings.DOCUSIGN_INTEGRATOR_KEY
    return {
        'X-DocuSign-Authentication': ET.tostring(creds),
        'Accept': 'application/json',
    }


HEADERS = get_headers()


def get_base_url():
    """ Get the base URL from which API requests must be made.

    DocuSign does not guarantee that this URL remains static, so query
    it every time we intend to use the API.
    """
    v2_base = settings.DOCUSIGN_API_BASE  # (Demo or production)
    resp = requests.get(v2_base + 'login_information', headers=HEADERS)

    return resp.json()['loginAccounts'][0]['baseUrl']


def affiliation_to_radio_value(participant):
    """ Map affiliation to a selectable value in the DocuSign template. """
    return AFFILIATION_MAPPING.get(participant.affiliation)


def prefilled_tabs(participant):
    """ Return tabs that are prefilled for the Releasor role. """
    e_contact = participant.emergency_info.emergency_contact
    tabs = {
        'textTabs': [
            {'tabLabel': "Emergency Contact", 'value': e_contact.name},
            {'tabLabel': "Emergency Contact Relation", 'value': e_contact.relationship},
        ],
        'numberTabs': [
            {
                'tabLabel': "Emergency Contact's Phone",
                'value': str(e_contact.cell_phone),
            },
            {'tabLabel': 'Phone number', 'value': str(participant.cell_phone)},
        ],
    }
    # Only pre-select affiliation if the participant has a known affiliation
    # (The 'S' affiliation does not map clearly to a category)
    docusign_affiliation = affiliation_to_radio_value(participant)
    if docusign_affiliation:
        tabs['radioGroupTabs'] = [
            {
                'groupName': 'Affiliation',
                'radios': [{'value': docusign_affiliation, 'selected': True}],
            }
        ]
    return tabs


def get_roles(
    participant=None, name=None, email=None, guardian_name=None, guardian_email=None
):
    """ Return the role definitions, with prefilled data if available.

    When we create the envelope, the waiver will be sent to the releasor (and a
    guardian, if one is given).
    """
    releasor = {
        'roleName': 'Releasor',
        'name': name or participant.name,
        'email': email or participant.email,
    }
    desk = {
        'roleName': 'MITOC Desk',
        'name': 'MITOC Desk',
        'email': 'mitocdesk@gmail.com',
    }

    # If there's a participant, copy over medical info & such to prefill form
    if participant:
        releasor['tabs'] = prefilled_tabs(participant)

    if not (guardian_name and guardian_email):
        return [releasor, desk]

    guardian = {
        'roleName': 'Parent or Guardian',
        'name': guardian_name,
        'email': guardian_email,
    }
    return [releasor, guardian, desk]


def sign_embedded(participant, releasor, envelope_id, base_url=None):
    """ Take a known user and go straight to the waiver flow.

    Normally, we would rely on a waiver being sent to a user's email address
    in order to know that they own the email address. However, in this case,
    we already know that the participant owns the email address, so we can
    go straight into the waiver flow.

    The releasor object is a standard role definition that has already been
    configured for use with a template, and has a 'clientUserId' assigned.
    """
    base_url = base_url or get_base_url()
    recipient_url = base_url + '/envelopes/{}/views/recipient'.format(envelope_id)
    user = {
        'userName': releasor['name'],
        'email': releasor['email'],
        'clientUserId': releasor['clientUserId'],
        'authenticationMethod': 'email',
        'returnUrl': 'https://mitoc-trips.mit.edu',
    }
    # Fetch a URL that can be used to sign the waiver (expires in 5 minutes)
    redir_url = requests.post(recipient_url, json=user, headers=HEADERS)
    return redir_url.json()['url']


def initiate_waiver(
    participant=None, name=None, email=None, guardian_name=None, guardian_email=None
):
    """ Create a waiver & send it to the participant (releasor).

    If the participant does not exist (i.e. somebody who's just signing with
    their name and email address), do not attempt to pre-fill the form.

    Returns the email address of the releasor, and an optional URL for
    embedded signing redirection (if None, callers should take no action).
    """
    if participant is None and not (name or email):
        raise ValueError("Participant or name/email required!")

    roles = get_roles(participant, name, email, guardian_name, guardian_email)
    releasor = roles[0]

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
        releasor['clientUserId'] = participant.pk

    base_url = get_base_url()
    env = requests.post(base_url + '/envelopes', json=new_env, headers=HEADERS)

    if participant:  # We need a participant to do embedded signing
        envelope_id = env.json()['envelopeId']
        redir_url = sign_embedded(participant, releasor, envelope_id, base_url)
    else:  # An email will be sent. No need to redirect
        redir_url = None

    return releasor['email'], redir_url
