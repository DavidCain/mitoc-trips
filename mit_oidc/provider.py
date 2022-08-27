from typing import Dict, List, TypedDict

from allauth.account.models import EmailAddress
from allauth.socialaccount import providers
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider


class Data(TypedDict):
    sub: str

    email: str
    email_verified: bool

    # Profile fields
    family_name: str
    given_name: str
    name: str
    preferred_username: str


# https://oidc.mit.edu/.well-known/openid-configuration
class MitOidcProvider(OAuth2Provider):
    id = 'mit_oidc'
    name = "MIT OIDC"

    def extract_uid(self, data: Data) -> str:
        return data['email']

    def get_default_scope(self):
        return ['email', 'openid', 'profile']

    def extract_common_fields(self, data: Data) -> Dict[str, str]:
        return dict(
            email=data['email'],
            # name=data.get("name"),
        )

    def extract_email_addresses(self, data) -> List[EmailAddress]:
        emails: List[str] = []
        email = data.get("email")
        if email and data.get("verified_email"):
            emails.append(EmailAddress(email=email, verified=True, primary=True))
        return emails


providers.registry.register(MitOidcProvider)
