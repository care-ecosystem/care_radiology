import logging

from django.conf import settings
from django.contrib.auth.models import AnonymousUser

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ParseError


from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care.emr.models.tag_config import TagConfig
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.services.dicom_service import (
    WebhookConflictError,
    process_study_webhook,
)

STATIC_API_KEY = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_WEBHOOK_SECRET']
VALID_MPPS_STATUSES = ["SCAN_STARTED", "SCAN_COMPLETED", "DISCONTINUED"]

logger = logging.getLogger(__name__)


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


    @action(
        detail=False,
        methods=["post"],
        url_path="status",
        permission_classes=[AllowAny], # Need to add throttling & limit based on expected volume
    )
    def handle_mpps(self, request):
        """
        Handle MPPS (Modality Performed Procedure Step) status updates from DICOM enabler.

        MPPS is part of the DICOM standard for tracking the status of imaging procedures.
        This webhook receives status updates and maps them to CARE ServiceRequest tags.

        Expected Payload:
        {
            "service_request_id": "uuid-of-service-request",
            "study_status": "STARTED" | "COMPLETED" | "DISCONTINUED" | "IN_PROGRESS"
        }

        Tag Mapping:
        - Status values must match TagConfig.display values for the facility
        - Each facility can have custom tag configurations
        - Tags are appended to ServiceRequest.tags array (duplicates prevented)

        Authentication:
        - Requires CARE_RADIOLOGY_WEBHOOK_SECRET in Authorization header

        Returns:
            200: Tag updated successfully or already exists
            400: Missing fields, invalid facility, or tag config not found
            401: Invalid API key
            404: ServiceRequest not found
            500: Database error
        """
        logger.info("[MPPS] Webhook received!")
        # Step 1: Authenticate
        authenticator = StaticAPIKeyAuthentication()
        user_auth_tuple = authenticator.authenticate(request)
        if user_auth_tuple is None:
            raise AuthenticationFailed("Invalid API key")

        # Step 2: Parse webhook data
        try:
            data = request.data
            logger.info(f"[MPPS] Received data: {data}")
        except ParseError:
            logger.error("[MPPS] Invalid JSON payload")
            return Response(
                {"detail": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Step 3: Extract fields
        service_request_id = data.get("service_request_id")
        study_status = data.get("study_status")
        logger.info(
            f"[MPPS] Extracted - SR: {service_request_id}, Status: {study_status}"
        )

        # Step 4: Validate required fields
        if not service_request_id or not study_status:
            logger.error("[MPPS] Missing required fields")
            return Response(
                {
                    "detail": "Missing required fields: service_request_id, study_status"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Step 5: Validate study_status value
        if study_status not in VALID_MPPS_STATUSES:
            logger.warning(f"[MPPS] Unexpected status: {study_status}")
            # Still process it, but log warning

        # Log the webhook
        RadiologyWebhookLogs.objects.create(raw_data=data, type="MPPS")
        logger.info("[MPPS] Webhook logged to database")

        # Step 6: Get ServiceRequest from CARE
        try:
            sr = ServiceRequest.objects.get(external_id=service_request_id)
            logger.info(f"[MPPS] ServiceRequest found: {sr.id}")
        except ServiceRequest.DoesNotExist:
            logger.error(
                f"[MPPS] ServiceRequest not found: {service_request_id}"
            )
            return Response(
                {"detail": f"Service request not found: {service_request_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Step 7: Get facility from ServiceRequest
        facility = sr.facility
        if not facility:
            logger.error("[MPPS] Facility not found for SR")
            return Response(
                {"detail": "Facility not found for service request"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(f"[MPPS] Facility found: {facility.external_id}")
        # Step 8: Get TagConfig for MPPS status
        try:
            tag_config = TagConfig.objects.filter(
                facility=facility, display=study_status  # e.g., "STARTED"
            ).first()

            if not tag_config:
                logger.error(f"[MPPS] Tag not found for status: {study_status}")
                return Response(
                    {
                        "detail": f"Tag configuration not found for status: {study_status}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tag_uuid = tag_config.external_id
            tag_id = tag_config.id
            logger.info(f"[MPPS] Tag found: {tag_uuid}")
        except Exception as e:
            logger.error(f"[MPPS] Error fetching tag: {str(e)}")
            return Response(
                {"detail": f"Error fetching tag configuration: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 9: Update ServiceRequest tags directly via Django ORM
        try:    
            tags = sr.tags or []
            logger.info(f"[MPPS] Current tags before update: {tags}")

            if tag_id in tags:
                logger.warning(
                    f"[MPPS] Tag {tag_id} already exists in SR {service_request_id}, skipping duplicate"
                )
                return Response(
                    {
                        "detail": "Tag already set for this service request",
                        "service_request_id": service_request_id,
                        "study_status": study_status,
                        "tag_id": tag_id,
                    },
                    status=status.HTTP_200_OK,
                )

            tags.append(tag_id)
            sr.tags = tags
            sr.save(
                update_fields=["tags"],
                performer="system:dicom-enabler-mpps",  # Track performer
                performer_details={"webhook_type": "MPPS", "study_status": study_status}
            )

            logger.info(f"[MPPS] Tag {tag_id} appended to ServiceRequest tags")
            logger.info(f"[MPPS] Updated tags: {sr.tags}")

        except Exception as e:
            logger.error(f"[MPPS] Error updating tags: {str(e)}")
            return Response(
                {"detail": f"Error updating tags: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 10: Return success
        logger.info("[MPPS] Success! MPPS status tag updated via direct database write")
        return Response(
            {
                "detail": "MPPS status tag updated successfully",
                "service_request_id": service_request_id,
                "study_status": study_status,
                "tag_id": tag_id,
                "tag_uuid": str(tag_uuid),
                "current_tags": sr.tags,
            },
            status=status.HTTP_200_OK,
        )