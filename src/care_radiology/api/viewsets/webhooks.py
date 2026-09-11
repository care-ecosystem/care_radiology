import logging

from care.emr.api.viewsets.base import emr_exception_handler
from care.emr.models.service_request import ServiceRequest
from care.utils.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care_radiology.api.specs.webhooks import WebhookMppsSpec, WebhookStudySpec
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.security.authentication import (
    StaticAPIKeyAuthentication,
    StaticAPIKeyAuthorization,
)
from care_radiology.services.dicom_service import (
    WebhookConflictError,
    process_mpps_webhook,
    process_study_webhook,
)

logger = logging.getLogger(__name__)


class WebhookViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

    # DICOM study completion webhook, links an uploaded study to a service request.
    @extend_schema(request=WebhookStudySpec)
    @action(
        detail=False,
        methods=["post"],
        url_path="study",
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[StaticAPIKeyAuthorization],
    )
    def save_webhook(self, request):
        data = request.data
        RadiologyWebhookLogs.objects.create(raw_data=data, type="SR-STUDY-INSERT")
        WebhookStudySpec.model_validate(data)

        try:
            record = process_study_webhook(data)
        except WebhookConflictError as e:
            return Response({"detail": e.message}, status=status.HTTP_409_CONFLICT)

        return Response(
            {"detail": "Webhook received and saved successfully", **({"record": record} if record is not None else {})},
            status=status.HTTP_200_OK,
        )

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
        logger.info("[MPPS] Webhook received!")
        request_data = WebhookMppsSpec.model_validate(request.data)
        logger.info("[MPPS] Extracted - SR: %s, Status: %s", request_data.service_request_id, request_data.study_status)

        RadiologyWebhookLogs.objects.create(raw_data=request.data, type="MPPS")
        logger.info("[MPPS] Webhook logged to database")

        service_request = get_object_or_404(ServiceRequest, external_id=request_data.service_request_id)
        logger.info("[MPPS] ServiceRequest found: %s", service_request.id)

        record = process_mpps_webhook(service_request, request_data.study_status)

        return Response(record, status=status.HTTP_200_OK)
