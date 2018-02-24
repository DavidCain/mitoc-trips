import xml.etree.cElementTree as ET

import requests

from ws import settings


def get_headers():
    """ Get standard headers to be used with every DocuSign API request. """
    creds = ET.Element('DocuSignCredentials')
    ET.SubElement(creds,      'Username').text = settings.DOCUSIGN_USERNAME
    ET.SubElement(creds,      'Password').text = settings.DOCUSIGN_PASSWORD
    ET.SubElement(creds, 'IntegratorKey').text = settings.DOCUSIGN_INTEGRATOR_KEY
    return {
        'X-DocuSign-Authentication': ET.tostring(creds),
        'Accept': 'application/json'
    }


HEADERS = get_headers()


def get_base_url():
    """ Get the base URL from which API requests must be made.

    DocuSign does not guarantee that this URL remains static, so query
    it every time we intend to use the API.
    """
    v2_base = 'https://demo.docusign.net/restapi/v2/'
    resp = requests.get(v2_base + 'login_information', headers=HEADERS)

    return resp.json()['loginAccounts'][0]['baseUrl']


def prefilled_tabs(participant):
    """ Return tabs that are prefilled for the Releasor role. """
    e_contact = participant.emergency_info.emergency_contact
    return {
        'textTabs': [
            {'tabLabel': "Emergency Contact", 'value': e_contact.name},
            {'tabLabel': "Emergency Contact Relation", 'value': e_contact.relationship},
        ],
        'numberTabs': [
            {'tabLabel': "Emergency Contact's Phone", 'value': str(e_contact.cell_phone)},
            {'tabLabel': 'Phone number', 'value': str(participant.cell_phone)}
        ]
    }


def initiate_waiver(participant=None, name=None, email=None,
                    guardian_name=None, guardian_email=None):
    """ Create a waiver & email it to the participant.

    If the participant does not exist (i.e. somebody who's just signing with
    their name and email address, do not attempt to pre-fill the form)

    TODO: We can flow straight into the document instead.
    docusign.com/developer-center/explore/features/embedding-docusign
    """
    if participant is None and not (name or email):
        raise ValueError("Participant or name/email required!")
    base_url = get_base_url()

    releasor = {
        'roleName': 'Releasor',
        'name': name or participant.name,
        'email': email or participant.email,
    }
    guardian = {
        'roleName': 'Parent or Guardian',
        'name': guardian_name,
        'email': guardian_email
    }
    if participant:
        releasor['tabs'] = prefilled_tabs(participant)
    roles = [releasor]
    if guardian_name and guardian_email:
        roles.append(guardian)

    # Create a new envelope
    new_env = {
        'status': 'sent',  # This will send an email to the Releasor
        'templateId': settings.DOCUSIGN_WAIVER_TEMPLATE_ID,
        'templateRoles': roles,
        'eventNotification': settings.DOCUSIGN_EVENT_NOTIFICATION
    }

    return requests.post(base_url + '/envelopes', json=new_env, headers=HEADERS)
