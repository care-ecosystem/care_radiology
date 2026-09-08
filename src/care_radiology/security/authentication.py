from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from care_radiology.settings import plugin_settings

STATIC_API_KEY = plugin_settings.CARE_RADIOLOGY_WEBHOOK_SECRET


class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")


class StaticAPIKeyAuthorization(BasePermission):
    def has_permission(self, request, view):
        api_key = request.headers.get("Authorization")
        return api_key == STATIC_API_KEY
