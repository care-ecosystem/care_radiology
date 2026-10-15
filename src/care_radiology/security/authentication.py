from config.ratelimit import ratelimit
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled
from rest_framework.permissions import BasePermission

from care_radiology.settings import plugin_settings

_RATE_LIMIT_SETTING_BY_URL_NAME = {
    "radiology_external-worklist": "CARE_RADIOLOGY_RATE_LIMIT_DICOM_WORKLIST",
    "radiology_external-upload": "CARE_RADIOLOGY_RATE_LIMIT_DICOM_UPLOAD_EXTERNAL",
    "radiology_external-update-status": "CARE_RADIOLOGY_RATE_LIMIT_WEBHOOK_STATUS",
}


class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        url_name = request.resolver_match.url_name
        setting_name = _RATE_LIMIT_SETTING_BY_URL_NAME.get(url_name)
        rate = getattr(plugin_settings, setting_name) if setting_name else settings.DJANGO_RATE_LIMIT
        if ratelimit(request, group=f"static-api-key:{url_name}", keys=["ip"], rate=rate):
            raise Throttled(detail="Too many requests. Please try again later.")

        api_key = request.headers.get("Authorization")
        if api_key == plugin_settings.CARE_RADIOLOGY_WEBHOOK_SECRET:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")

    def authenticate_header(self, request):
        # A value here makes DRF answer a failed authentication with 401 instead of 403.
        return "Api-Key"


class StaticAPIKeyAuthorization(BasePermission):
    def has_permission(self, request, view):
        api_key = request.headers.get("Authorization")
        return api_key == plugin_settings.CARE_RADIOLOGY_WEBHOOK_SECRET
