from django.conf import settings
from django.contrib.auth.models import AnonymousUser
import logging
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, ParseError


from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.models.radiology_service_request import (
    RadiologyServiceRequest,
)

STATIC_API_KEY = settings.PLUGIN_CONFIGS["care_radiology"][
    "CARE_RADIOLOGY_WEBHOOK_SECRET"
]


class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")


logger = logging.getLogger(__name__)


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

        RadiologyWebhookLogs.objects.create(
            raw_data=data, type="SR-STUDY-INSERT"
        )
        if not isinstance(data, dict):
            return Response(
                {"detail": "JSON object expected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if data.get("service_request_id") and data.get("study_id"):
            try:
                sr = ServiceRequest.objects.get(
                    external_id=data["service_request_id"]
                )
            except ServiceRequest.DoesNotExist:
                return Response(
                    {"detail": "No matching service request"},
                    status=status.HTTP_409_CONFLICT,
                )
            (study, ds_created) = DicomStudy.objects.get_or_create(
                dicom_study_uid=data.get("study_id"),
                patient=sr.patient,
                defaults={},
            )
            if sr and study:
                (rsr, rsr_created) = (
                    RadiologyServiceRequest.objects.update_or_create(
                        service_request=sr,
                        dicom_study=study,
                        defaults={"raw_data": data},
                    )
                )

            return Response(
                {
                    "detail": "Webhook received and saved successfully",
                    "record": {
                        "external_id": rsr.external_id,
                        "data": rsr.raw_data,
                    },
                },
                status=status.HTTP_200_OK,
            )

        elif data.get("patient_id") and data.get("study_id"):
            patient = Patient.objects.filter(
                instance_identifiers__contains=[
                    {"value": data.get("patient_id")}
                ]
            ).first()
            if not patient:
                return Response(
                    {"detail": "No matching patient"},
                    status=status.HTTP_409_CONFLICT,
                )
            (study, ds_created) = DicomStudy.objects.get_or_create(
                dicom_study_uid=data.get("study_id"),
                patient=patient,
                defaults={},
            )
            if patient and study:
                return Response(
                    {
                        "detail": "Webhook received and saved successfully",
                        "record": {
                            "external_id": study.external_id,
                            "data": data,
                        },
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
        url_path="mpps",
        permission_classes=[AllowAny],
    )
    def handle_mpps(self, request):
        """
        Handle MPPS status updates from DICOM enabler
        Updates ServiceRequest tags in CARE
        """
        logger.info("[MPPS] Webhook received!")
        print("[MPPS] Webhook received!")  # Also print to console
        # Step 1: Authenticate
        authenticator = StaticAPIKeyAuthentication()
        try:
            authenticator.authenticate(request)
            logger.info("[MPPS] Authentication passed")
        except AuthenticationFailed:
            logger.error("[MPPS] Authentication failed")
            return Response(
                {"detail": "Invalid API key"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Step 2: Parse webhook data
        try:
            data = request.data
            logger.info(f"[MPPS] Received data: {data}")
            print(f"[MPPS] Received data: {data}")
        except ParseError:
            logger.error("[MPPS] Invalid JSON payload")
            return Response(
                {"detail": "Invalid JSON payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Step 3: Extract fields
        service_request_id = data.get("service_request_id")
        mpps_status = data.get("mpps_status")
        study_id = data.get("study_id")
        logger.info(
            f"[MPPS] Extracted - SR: {service_request_id}, Status: {mpps_status}"
        )

        # Step 4: Validate required fields
        if not service_request_id or not mpps_status:
            logger.error("[MPPS] Missing required fields")
            return Response(
                {
                    "detail": "Missing required fields: service_request_id, mpps_status"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Log the webhook
        RadiologyWebhookLogs.objects.create(raw_data=data, type="MPPS")
        logger.info("[MPPS] Webhook logged to database")

        # Step 5: Get ServiceRequest from CARE
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

        # Step 6: Get facility from ServiceRequest
        facility = sr.facility
        if not facility:
            logger.error("[MPPS] Facility not found for SR")
            return Response(
                {"detail": "Facility not found for service request"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(f"[MPPS] Facility found: {facility.external_id}")
        # Step 7: Get TagConfig for MPPS status
        from care.emr.models.tag_config import TagConfig

        try:
            tag_config = TagConfig.objects.filter(
                facility=facility, display=mpps_status  # e.g., "STARTED"
            ).first()

            if not tag_config:
                logger.error(f"[MPPS] Tag not found for status: {mpps_status}")
                return Response(
                    {
                        "detail": f"Tag configuration not found for status: {mpps_status}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            tag_uuid = tag_config.external_id
            logger.info(f"[MPPS] Tag found: {tag_uuid}")
        except Exception as e:
            logger.error(f"[MPPS] Error fetching tag: {str(e)}")
            return Response(
                {"detail": f"Error fetching tag configuration: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 8: Call CARE's set_tags API via HTTP with stored authentication
        try:
            import requests
            from django.core.cache import cache

            set_tags_url = f"http://localhost:9000/api/v1/facility/{facility.external_id}/service_request/{service_request_id}/set_tags/"

            payload = {"tags": [str(tag_uuid)]}
            logger.info(f"[MPPS] Calling set_tags API: {set_tags_url}")
            logger.info(f"[MPPS] Payload: {payload}")

            # Step 8a: Get cached access token or fetch new one
            access_token = cache.get("admin_access_token")

            if not access_token:
                logger.info(
                    "[MPPS] Access token not in cache, fetching new one..."
                )
                login_url = "http://localhost:9000/api/v1/auth/login/"
                login_payload = {"username": "admin", "password": "admin"}

                login_response = requests.post(login_url, json=login_payload)
                login_response.raise_for_status()

                access_token = login_response.json().get("access")
                # Cache the token for 10 minutes (600 seconds)
                cache.set("admin_access_token", access_token, 600)
                logger.info("[MPPS] New access token obtained and cached")
            else:
                logger.info("[MPPS] Using cached access token")

            # Step 8b: Call set_tags with the token
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            }

            response = requests.post(
                set_tags_url, json=payload, headers=headers
            )
            logger.info(f"[MPPS] set_tags response: {response.status_code}")
            response.raise_for_status()

        except Exception as e:
            logger.error(f"[MPPS] Error calling set_tags API: {str(e)}")
            return Response(
                {"detail": f"Error calling set_tags API: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Step 9: Return success
        logger.info("[MPPS] Success! Tag updated")
        return Response(
            {
                "detail": "MPPS status tag updated successfully",
                "service_request_id": service_request_id,
                "mpps_status": mpps_status,
                "tag_uuid": str(tag_uuid),
            },
            status=status.HTTP_200_OK,
        )
