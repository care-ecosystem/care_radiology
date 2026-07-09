from django.conf import settings

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db.models import Q, OuterRef, Exists
from django.contrib.auth.models import AnonymousUser

from care.emr.models.device import Device
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care.emr.resources.encounter.spec import EncounterRetrieveSpec
from care.emr.resources.service_request.spec import ServiceRequestReadSpec
from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.study_report import StudyReport
from care_radiology.services.dicom_service import (
    DicomUploadError,
    fetch_study,
    link_service_request_to_study,
    upload_dicom_file,
)


STATIC_API_KEY = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_WEBHOOK_SECRET']

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


class DicomViewSet(ViewSet):

    # A dummy API for JWT verification called by nginx-proxy for dicomweb requests
    @action(detail=False, methods=["get"], url_path="authenticate")
    def authenticate(self, _):
        return Response(status=200)

    @action(
        detail=False,
        methods=["get"],
        url_path="worklist",
        permission_classes = [AllowAny]
    )
    def worklist(self, request):
        # Manually authenticate
        authenticator = StaticAPIKeyAuthentication()
        user_auth_tuple = authenticator.authenticate(request)
        if user_auth_tuple is None:
            raise AuthenticationFailed("Invalid API key")

        modality = request.query_params.get("modality", None)
        from_date = parse_date(request.query_params.get("from"))
        to_date = parse_date(request.query_params.get("to"))
        facility = request.query_params.get("facility")

        results = get_service_requests(
            modality=modality,
            from_date=from_date,
            to_date=to_date,
            limit=1000,  # optional, default is 1000
        )

        return Response(data={
            "status": "success",
            "results": results
        }, status=200)

    # DCM Files upload
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        patient = get_object_or_404(Patient, external_id=request.data.get("patient_id"))
        dcm_file = request.FILES.get("file")

        if not AuthorizationController.call("can_write_patient_obj", self.request.user, patient):
            raise PermissionDenied(f"You do not have permission to upload DICOM for this patient")

        try:
            result = upload_dicom_file(patient, dcm_file)
            return Response(
                data={
                    "message": "DICOM files uploaded to DCM4CHE successfully",
                    **result,
                },
                status=201,
            )
            if upload_response.status_code in [200, 201]:
                refenrenced_sop = d_find(
                    upload_response.json(), DICOM_TAG.ReferencedSOPSQ.value
                )[0]

                instance_uid = d_find(
                    refenrenced_sop, DICOM_TAG.ReferencedInstanceUID.value
                )[0]

                study_uid = d_find(
                    d_query_instance(instance_uid), DICOM_TAG.StudyInstanceUID.value
                )[0]

                studies_qs = DicomStudy.objects.annotate(
                    has_report=Exists(
                        StudyReport.objects.filter(study=OuterRef('pk'))
                    )
                )

                (dicom_study, is_created) = DicomStudy.objects.update_or_create(
                    dicom_study_uid=study_uid,
                    patient=patient,
                    defaults={},
                )

                dicom_study = studies_qs.get(pk=dicom_study.pk)

                # Bust the study from cache
                key = f"radiology:dicom:study:{study_uid}"
                cache.delete(key)

                return Response(
                    data={
                        "message": "DICOM file uploaded to Orthanc successfully",
                        "study_uid": study_uid,
                        "study": fetch_study(dicom_study),
                    },
                    status=201,
                )

            else:
                import logging
                logger = logging.getLogger(__name__)
                logger.info("Inside the else block")
                logger.info(f"Upload Response Status: {upload_response.status_code}")

                logger.error(f"Response Body: {upload_response.text}")
                logger.error("\n")
                
                logger.error(f"Response JSON: {upload_response.json()}")  # if response is JSON

                return Response(
                    data={
                        "error": "Failed to upload to DCM4CHE",
                        "status_code": upload_response.status_code,
                    },
                    status=502,
                )


        except Exception as e:
            return Response(
                data={"error": e.message, **e.extra},
                status=e.status_code,
            )

    # DCM Files upload via static API key (no user auth required)
    @action(
        detail=False,
        methods=["post"],
        url_path="upload-dicom-external",
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[StaticAPIKeyAuthorization],
    )
    def upload_with_key(self, request):
        patient = get_object_or_404(Patient, external_id=request.data.get("patient_id"))
        dcm_file = request.FILES.get("file")

        try:
            result = upload_dicom_file(patient, dcm_file)
            return Response(
                data={
                    "message": "DICOM files uploaded to DCM4CHE successfully",
                    **result,
                },
                status=201,
            )
        except DicomUploadError as e:
            return Response(
                data={"error": e.message, **e.extra},
                status=e.status_code,
            )

    # Link an already-uploaded study to a service request, called once all files for
    # a study have finished uploading via `upload`/`upload-dicom-external`.
    @action(detail=False, methods=["post"], url_path="link-service-request")
    def link_service_request(self, request):
        service_request_id = request.data.get("service_request_id")
        study_uid = request.data.get("study_uid")

        if not service_request_id or not study_uid:
            return Response(
                {"detail": "service_request_id and study_uid are required"}, status=400
            )

        service_request = get_object_or_404(ServiceRequest, external_id=service_request_id)
        if not AuthorizationController.call("can_write_service_request", self.request.user, service_request):
            raise PermissionDenied(f"You do not have permission to update this service request")

        record = link_service_request_to_study(service_request, study_uid)

        return Response(
            {
                "detail": "Service request linked to study successfully",
                "record": record,
            },
            status=200,
        )

    # Get list of studies
    @action(detail=False, methods=["get"], url_path="studies")
    def get_studies(self, request):
        patient_external_id = request.query_params.get("patientId")
        patient = get_object_or_404(Patient, external_id=patient_external_id)
        if not AuthorizationController.call("can_view_patient_obj", self.request.user, patient):
            raise PermissionDenied(f"You do not have permission to view this patient")

        report_exists = StudyReport.objects.filter(study=OuterRef('pk'))
        studies = DicomStudy.objects.filter(patient__external_id=patient_external_id).annotate(has_report=Exists(report_exists))

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {
                executor.submit(fetch_study, study): study
                for study in studies
            }
            for future in as_completed(future_to_study):
                result = future.result()
                if result is not None:
                    results.append(result)

        return Response(results, status=200)

    @action(
        detail=False,
        methods=["get"],
        url_path="service-requests",
    )
    def get_servicerequests(self, request):
        service_request_external_id = request.query_params.get("serviceRequestId")

        service_request = ServiceRequest.objects.get(external_id=service_request_external_id)
        if not AuthorizationController.call("can_write_service_request", self.request.user, service_request):
            raise PermissionDenied(f"You do not have permission to view this service request")

        report_exists = StudyReport.objects.filter(study=OuterRef("dicom_study__pk"))
        tsr = RadiologyServiceRequest.objects.filter(
            service_request__external_id=service_request_external_id,
            dicom_study__dicom_study_uid__isnull=False,
        ).annotate(has_report=Exists(report_exists)).select_related("dicom_study")

        for r in tsr:
            r.dicom_study.has_report = r.has_report


        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {
                executor.submit(fetch_study, r.dicom_study): r
                for r in tsr
            }

            for future in as_completed(future_to_study):
                r = future_to_study[future]
                service_request = ServiceRequestReadSpec.serialize(r.service_request).to_json()
                service_request["encounter"] = EncounterRetrieveSpec.serialize(r.service_request.encounter).to_json()

                results.append({
                    "service_request": service_request,
                    "dicom_study": future.result(),
                })

        return Response(
            results,
            status=200,
        )


def get_service_requests(
    *,
    from_date=None,
    to_date=None,
    modality=None,
    limit=1000,
):
    filters = Q(status="active", deleted=False)

    if modality:
        device_location_ids = Device.objects.filter(
            registered_name__iexact=modality
        ).values_list("current_location_id", flat=True)
        filters &= Q(activity_definition__locations__overlap=device_location_ids)

    if from_date:
        filters &= Q(created_date__gte=from_date)

    if to_date:
        filters &= Q(created_date__lte=to_date)

    qs = ServiceRequest.objects.filter(filters).select_related(
        "patient", "facility", "activity_definition"
    )[:limit]

    results = []
    for sr in qs:
        results.append(
            {
                "service_request": {
                    "id": sr.id,
                    "external_id": sr.external_id,
                    "name": sr.activity_definition.title,
                    "date": sr.created_date,
                    "meta": sr.meta
                },
                "facility": {
                    "id": sr.facility.external_id,
                    "name": sr.facility.name
                },
                "patient": {
                    "id": sr.patient.id,
                    "external_id": sr.patient.external_id,
                    "name": sr.patient.name,
                    "address": sr.patient.address,
                    "phone_number": sr.patient.phone_number,
                    "gender": sr.patient.gender,
                    "age": sr.patient.age
                }
            }
        )

    return results


# Date utils ------------------------------------------------------------------
def parse_date(date_str):
    if not date_str:
        return None
    try:
        # Try full datetime first
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback to date-only if time not provided
        return datetime.strptime(date_str, "%Y-%m-%d")
