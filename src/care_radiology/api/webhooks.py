from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ParseError


from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.services.dicom_service import (
    WebhookConflictError,
    process_study_webhook,
)

STATIC_API_KEY = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_WEBHOOK_SECRET']


class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")


class WebhookViewSet(ViewSet):
    @action(
        detail=False,
        methods=["post"],
        url_path="study",
        permission_classes=[AllowAny],
    )
    def save_webhook(self, request):
        # Manually authenticate
        authenticator = StaticAPIKeyAuthentication()
        user_auth_tuple = authenticator.authenticate(request)
        if user_auth_tuple is None:
            raise AuthenticationFailed("Invalid API key")

        try:
            data = request.data
        except ParseError:
            return Response(
                {"detail": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        RadiologyWebhookLogs.objects.create(raw_data=data, type="SR-STUDY-INSERT")
        if not isinstance(data, dict):
            return Response(
                {"detail": "JSON object expected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            record = process_study_webhook(data)
        except WebhookConflictError as e:
            return Response(
                {"detail": e.message},
                status=status.HTTP_409_CONFLICT,
            )

        if record is not None:
            return Response(
                {
                    "detail": "Webhook received and saved successfully",
                    "record": record,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "detail": "Webhook received and saved successfully",
            },
            status=status.HTTP_200_OK,
        )
