import logging

from care.emr.api.viewsets.base import emr_exception_handler
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care_radiology.api.specs.webhooks import WebhookMppsSpec
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.security.authentication import (
    StaticAPIKeyAuthentication,
    StaticAPIKeyAuthorization,
)
from care_radiology.services.dicom_service import process_mpps_webhook

logger = logging.getLogger(__name__)


@extend_schema(tags=["Radiology: Webhooks"])
class WebhookViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

    # MPPS status update, mapped to a ServiceRequest tag.
    @extend_schema(request=WebhookMppsSpec)
    @action(
        detail=False,
        methods=["post"],
        url_path="status",
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[StaticAPIKeyAuthorization],
    )
    def handle_mpps(self, request):
        logger.info("[MPPS] Webhook received")
        request_data = WebhookMppsSpec.model_validate(request.data)
        logger.info("[MPPS] Extracted - SR: %s, Status: %s", request_data.service_request_id, request_data.study_status)

        RadiologyWebhookLogs.objects.create(raw_data=request.data, type="MPPS")
        logger.info("[MPPS] Webhook logged to database")

        record = process_mpps_webhook(request_data.service_request_id, request_data.study_status)

        return Response(record, status=status.HTTP_200_OK)
