""" A module for interacting with MIT's ancient version of Mailman.

Mailman 3 has a full API that's much more user friendly, but we're stuck on Mailman 2.1.34
(previously 2.1.6 - MIT's IS&T recently upgraded to 2.1.34, getting HTTPS support!)
"""
import urllib.parse

import requests


def _post(url: str, **kwargs):
    """Post to any Mailman URL, including a user agent.

    (If MIT sees a *ton* of requests coming from our IP addresses, it's
    important they know exactly how to contact us)
    """
    assert url.startswith('https://mailman.mit.edu/mailman/')
    headers = {
        **kwargs.pop('headers', {}),
        'user-agent': 'mitoc-trips (https://mitoc-trips.mit.edu/contact)',
    }
    # Waiting more than a few seconds will make these requests hang a *long* time
    return requests.post(url, headers=headers, timeout=5, **kwargs)


def unsubscribe(email: str, listname: str):
    """Request to be unsubscribed from a Mailman list.

    If the user is already subscribed, then a confirmation email is sent.
    If not subscribed, no email is sent.
    """
    if listname.endswith('@mit.edu'):
        listname = listname[: listname.find('@mit.edu')]

    url = urllib.parse.urljoin('https://mailman.mit.edu/mailman/options/', listname)
    return _post(url, data={'email': email, 'login-unsub': 'Unsubscribe'})
