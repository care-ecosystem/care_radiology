from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from care_radiology.constants import WEBHOOK_SECRET


class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        # WEBHOOK_SECRET validates on first comparison (lazy evaluation)
        if api_key == WEBHOOK_SECRET:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")


class StaticAPIKeyAuthorization(BasePermission):
    def has_permission(self, request, view):
        api_key = request.headers.get("Authorization")
        # WEBHOOK_SECRET validates on first comparison (lazy evaluation)
        return api_key == WEBHOOK_SECRET
