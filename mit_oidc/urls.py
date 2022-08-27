from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns

from .provider import MitOidcProvider

urlpatterns = default_urlpatterns(MitOidcProvider)
