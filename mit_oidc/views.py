import requests
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)

from .provider import MitOidcProvider


class CustomAdapter(OAuth2Adapter):
    provider_id = MitOidcProvider.id

    # https://oidc.mit.edu/.well-known/openid-configuration
    access_token_url = 'https://oidc.mit.edu/token'
    authorize_url = "https://oidc.mit.edu/authorize"
    profile_url = 'https://oidc.mit.edu/userinfo'

    def complete_login(self, request, app, access_token, **kwargs):
        resp = requests.get(
            self.profile_url,
            headers={'Authorization': f'Bearer {access_token.token}'},
            timeout=10,
            # params={"access_token": access_token.token, "alt": "json"},
        )
        # Note that MIT OIDC returns errors in *HTML* (it's Apache Tomcat). Ugh.
        if resp.status_code == 403:
            raise ValueError(resp.content)
        extra_data = resp.json()
        return self.get_provider().sociallogin_from_response(request, extra_data)


oauth2_login = OAuth2LoginView.adapter_view(CustomAdapter)
oauth2_callback = OAuth2CallbackView.adapter_view(CustomAdapter)
