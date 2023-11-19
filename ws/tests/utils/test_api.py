import unittest

from django.http import HttpRequest

from ws.utils import api

TOKEN = ".".join(
    [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Header
        "eyJuYW1lIjoiVGltIEJlYXZlciIsImlhdCI6MTUxNjIzOTAyMn0",  # Payload
        "PDH9nL66SBR9YbeodfpSX_tLL3MhLfglLo4f-OEc49k",  # Signature
    ]
)


class JwtTests(unittest.TestCase):
    def test_raises_valueerror_on_non_bearer_token(self):
        request = HttpRequest()
        request.META["HTTP_AUTHORIZATION"] = TOKEN
        with self.assertRaises(ValueError):
            api.jwt_token_from_headers(request)

    def test_raises_valueerror_on_missing_token(self):
        request = HttpRequest()
        self.assertNotIn("HTTP_AUTHORIZATION", request.META)
        with self.assertRaises(ValueError):
            api.jwt_token_from_headers(request)

    def test_auth_token_extracted(self):
        """A JWT is extracted from a bearer token."""
        request = HttpRequest()
        request.META["HTTP_AUTHORIZATION"] = f"Bearer: {TOKEN}"
        self.assertEqual(api.jwt_token_from_headers(request), TOKEN)
