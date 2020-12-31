from datetime import datetime, timedelta

import jwt


def jwt_token_from_headers(request):
    """ Extract a JWT token from the Bearer header. """
    http_auth = request.META.get('HTTP_AUTHORIZATION')
    if not (http_auth and http_auth.startswith('Bearer: ')):
        raise ValueError('token missing')
    return http_auth.split()[1]


def bearer_jwt(secret: str, **payload) -> str:
    """Express a JWT as a Bearer token, meant for use with `Authorization` HTTP header.

    A few MITOC repositories are configured to talk to each other by using
    requests signed with shared secrets. For example, the `mitoc-member`
    repository can ask this project for all the emails known to be linked to a
    given email. This repository can ask the gear database for membership
    information.
    """
    expires = datetime.utcnow() + timedelta(minutes=15)
    token = jwt.encode({**payload, 'exp': expires}, secret, algorithm="HS256")
    return f'Bearer: {token}'
