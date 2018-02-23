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


def initiate_waiver(participant):
    """ Create a waiver & email it to the participant.

    TODO: We can flow straight into the document instead.
    docusign.com/developer-center/explore/features/embedding-docusign
    """
    base_url = get_base_url()

    # Create a new envelope
    new_env = {
        'status': 'sent',  # This will send an email to the Releasor
        'templateId': settings.DOCUSIGN_WAIVER_TEMPLATE_ID,
        'templateRoles': [
            {'name': participant.name,
             'roleName': 'Releasor',
             'email': participant.email
             }
        ],
        'eventNotification': settings.DOCUSIGN_EVENT_NOTIFICATION
    }

    return requests.post(base_url + '/envelopes', json=new_env, headers=HEADERS)
