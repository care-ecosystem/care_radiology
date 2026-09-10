import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from care.emr.models.device import Device
from care.emr.models.encounter import Encounter
from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care.facility.models import Facility
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.security.authentication import (
    StaticAPIKeyAuthentication,
    StaticAPIKeyAuthorization,
)
from care_radiology.services.dicom_service import (
    DicomUploadError,
    fetch_study,
    link_service_request_to_study,
    upload_dicom_file,
)
from care_radiology.utils.dicom import parse_date
from care_radiology.utils.patient import get_patient_uhid

logger = logging.getLogger(__name__)


class DicomViewSet(ViewSet):
    def _authorize_read_radiology_data(self, facility):
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

    def _authorize_write_radiology_data(self, facility):
        if not AuthorizationController.call("can_write_radiology_data", self.request.user, facility):
            raise PermissionDenied("You do not have permission to write radiology data for this facility")

    # A dummy API for JWT verification called by nginx-proxy for dicomweb requests
    @action(detail=False, methods=["get"], url_path="authenticate")
    def authenticate(self, _):
        return Response(status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path="worklist",
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[StaticAPIKeyAuthorization],
    )
    def worklist(self, request):
        modality = request.query_params.get("modality", None)
        from_date = parse_date(request.query_params.get("from"))
        to_date = parse_date(request.query_params.get("to"))
        facility_external_id = request.query_params.get("facility")
        facility = get_object_or_404(Facility, external_id=facility_external_id) if facility_external_id else None

        results = get_service_requests(
            modality=modality,
            from_date=from_date,
            to_date=to_date,
            facility=facility,
            limit=1000,
        )

        return Response(data={"status": "success", "results": results}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        facility_id = request.data.get("facility_id")
        if not facility_id:
            return Response({"detail": "facility_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        patient = get_object_or_404(Patient, external_id=request.data.get("patient_id"))
        facility = get_object_or_404(Facility, external_id=facility_id)
        dcm_file = request.FILES.get("file")

        if not AuthorizationController.call("can_write_patient_obj", request.user, patient):
            raise PermissionDenied("You do not have permission to upload DICOM for this patient")
        self._authorize_write_radiology_data(facility)

        try:
            result = upload_dicom_file(patient, dcm_file)
            return Response(
                data={
                    "message": "DICOM files uploaded to DCM4CHE successfully",
                    **result,
                },
                status=status.HTTP_201_CREATED,
            )
        except DicomUploadError as e:
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
                status=status.HTTP_201_CREATED,
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
                {"detail": "service_request_id and study_uid are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service_request = get_object_or_404(ServiceRequest, external_id=service_request_id)
        if not AuthorizationController.call("can_write_service_request", request.user, service_request):
            raise PermissionDenied("You do not have permission to update this service request")
        self._authorize_write_radiology_data(service_request.facility)

        record = link_service_request_to_study(service_request, study_uid)

        return Response(
            {
                "detail": "Service request linked to study successfully",
                "record": record,
            },
            status=status.HTTP_200_OK,
        )

    def _studies_for_encounter(self, encounter_external_id):
        encounter = get_object_or_404(Encounter, external_id=encounter_external_id)

        if not AuthorizationController.call("can_view_encounter_obj", self.request.user, encounter):
            raise PermissionDenied("You do not have permission to view this encounter")
        self._authorize_read_radiology_data(encounter.facility)

        radiology_service_requests = RadiologyServiceRequest.objects.filter(
            service_request__encounter=encounter,
            service_request__deleted=False,
            dicom_study__deleted=False,
            dicom_study__dicom_study_uid__isnull=False,
        ).select_related("dicom_study")

        return list({r.dicom_study_id: r.dicom_study for r in radiology_service_requests}.values())

    def _studies_for_service_request(self, service_request_external_id):
        service_request = get_object_or_404(ServiceRequest, external_id=service_request_external_id)

        if not AuthorizationController.call("can_read_service_request", self.request.user, service_request):
            raise PermissionDenied("You do not have permission to view this service request")
        self._authorize_read_radiology_data(service_request.facility)

        radiology_service_requests = RadiologyServiceRequest.objects.filter(
            service_request=service_request,
            dicom_study__deleted=False,
            dicom_study__dicom_study_uid__isnull=False,
        ).select_related("dicom_study")

        return list({r.dicom_study_id: r.dicom_study for r in radiology_service_requests}.values())

    @action(detail=False, methods=["get"], url_path="studies")
    def get_studies(self, request):
        encounter_external_id = request.query_params.get("encounterId")
        service_request_external_id = request.query_params.get("serviceRequestId")

        if not encounter_external_id and not service_request_external_id:
            return Response(
                {"detail": "Either encounterId or serviceRequestId is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if service_request_external_id:
            studies = self._studies_for_service_request(service_request_external_id)
        else:
            studies = self._studies_for_encounter(encounter_external_id)

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {executor.submit(fetch_study, study): study for study in studies}
            for future in as_completed(future_to_study):
                result = future.result()
                if result is not None:
                    results.append(result)

        return Response(results, status=status.HTTP_200_OK)


def get_service_requests(
    *,
    from_date=None,
    to_date=None,
    modality=None,
    facility=None,
    limit=1000,
):
    filters = Q(status="active", deleted=False)

    if facility:
        filters &= Q(facility=facility)

    if modality:
        device_location_ids = Device.objects.filter(registered_name__iexact=modality).values_list(
            "current_location_id", flat=True
        )
        filters &= Q(activity_definition__locations__overlap=device_location_ids)

    if from_date:
        filters &= Q(created_date__gte=from_date)

    if to_date:
        filters &= Q(created_date__lte=to_date)

    logger.info(
        "Service Request filters - modality=%s, from_date=%s, to_date=%s, facility=%s",
        modality,
        from_date,
        to_date,
        facility.external_id if facility else None,
    )

    qs = ServiceRequest.objects.filter(filters).select_related(
        "patient", "facility", "activity_definition", "created_by"
    )[:limit]

    results = []
    for sr in qs:
        body_site = None
        description = None
        procedure_id = None
        created_by = None
        patient_uhid = None

        if sr.activity_definition is not None:
            if sr.activity_definition.body_site is not None:
                body_site = sr.activity_definition.body_site.get("display")
            if sr.activity_definition.code is not None:
                description = sr.activity_definition.code.get("display")
                procedure_id = sr.activity_definition.code.get("code")

        if sr.created_by is not None:
            created_by = {
                "prefix": sr.created_by.prefix,
                "first_name": sr.created_by.first_name,
                "last_name": sr.created_by.last_name,
            }

        if sr.patient is not None:
            patient_uhid = get_patient_uhid(sr.patient)

        results.append(
            {
                "service_request": {
                    "id": sr.id,
                    "external_id": sr.external_id,
                    "name": sr.activity_definition.title,
                    "date": sr.created_date,
                    "meta": sr.meta,
                    "body_site": body_site,
                    "description": description,
                    "modality": modality,
                    "procedure_id": procedure_id,
                    "created_by": created_by,
                    "priority": sr.priority,
                    "technician_instruction": sr.note,
                    "patient_instruction": sr.patient_instruction,
                },
                "facility": {"id": sr.facility.external_id, "name": sr.facility.name},
                "patient": {
                    "id": sr.patient.id,
                    "external_id": sr.patient.external_id,
                    "name": sr.patient.name,
                    "address": sr.patient.address,
                    "phone_number": sr.patient.phone_number,
                    "gender": sr.patient.gender,
                    "age": sr.patient.age,
                    "patient_uhid": patient_uhid,
                },
            }
        )

    return results
