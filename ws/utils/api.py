from datetime import timedelta
from typing import Any

import jwt
from django.http import HttpRequest
from django.utils import timezone


def jwt_token_from_headers(request: HttpRequest) -> str:
    """Extract a JWT token from the Bearer header."""
    http_auth: str = request.META.get("HTTP_AUTHORIZATION", "")
    if not (http_auth and http_auth.startswith("Bearer: ")):
        raise ValueError("token missing")
    return http_auth.split()[1]


def bearer_jwt(secret: str, **payload: Any) -> str:
    """Express a JWT as a Bearer token, meant for use with `Authorization` HTTP header.

    A few MITOC repositories are configured to talk to each other by using
    requests signed with shared secrets. For example, Lambdas in the `mitoc-aws`
    repository can ask this project for all the emails known to be linked to a
    given email. This repository can ask the gear database for dues/waiver
    information.
    """
    expires = timezone.now() + timedelta(minutes=15)
    token = jwt.encode({**payload, "exp": expires}, secret, algorithm="HS256")
    return f"Bearer: {token}"
