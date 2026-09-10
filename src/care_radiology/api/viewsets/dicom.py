from concurrent.futures import ThreadPoolExecutor, as_completed

from care.emr.api.viewsets.base import emr_exception_handler
from care.emr.models.encounter import Encounter
from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care.facility.models import Facility
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care_radiology.api.specs.dicom import DicomStudiesQuerySpec, DicomStudyLinkSpec, DicomWorklistQuerySpec
from care_radiology.constants import DICOM_FILE_EXTENSIONS
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
from care_radiology.services.worklist_service import get_service_requests
from care_radiology.utils.dicom import parse_date


class DicomViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

    def _authorize_read_radiology_data(self, facility):
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

    def _authorize_write_radiology_data(self, facility):
        if not AuthorizationController.call("can_write_radiology_data", self.request.user, facility):
            raise PermissionDenied("You do not have permission to write radiology data for this facility")

    def _handle_dicom_upload(self, patient, dcm_file):
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
                data={"errors": [{"type": "dicom_upload_error", "msg": e.message, **e.extra}]},
                status=e.status_code,
            )

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
        query = DicomWorklistQuerySpec(**request.query_params.dict())
        facility = get_object_or_404(Facility, external_id=query.facility_id)

        results = get_service_requests(
            modality=query.modality,
            from_date=parse_date(query.from_date),
            to_date=parse_date(query.to_date),
            facility=facility,
            limit=1000,
        )

        return Response(data={"status": "success", "results": results}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        facility_id = request.data.get("facility_id")
        dcm_file = request.FILES.get("file")

        errors = {}
        if not facility_id:
            errors["facility_id"] = "This value is required"
        if not dcm_file:
            errors["file"] = "This value is required"
        elif not dcm_file.name.lower().endswith(DICOM_FILE_EXTENSIONS):
            errors["file"] = "Only .dcm and .dicom files are supported"
        if errors:
            raise ValidationError(errors)

        patient = get_object_or_404(Patient, external_id=request.data.get("patient_id"))
        facility = get_object_or_404(Facility, external_id=facility_id)

        if not AuthorizationController.call("can_write_patient_obj", request.user, patient):
            raise PermissionDenied("You do not have permission to upload DICOM for this patient")
        self._authorize_write_radiology_data(facility)

        return self._handle_dicom_upload(patient, dcm_file)

    # DCM Files upload via static API key (no user auth required)
    @action(
        detail=False,
        methods=["post"],
        url_path="upload-dicom-external",
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[StaticAPIKeyAuthorization],
    )
    def upload_with_key(self, request):
        dcm_file = request.FILES.get("file")
        if not dcm_file:
            raise ValidationError({"file": "This value is required"})

        patient = get_object_or_404(Patient, external_id=request.data.get("patient_id"))

        return self._handle_dicom_upload(patient, dcm_file)

    # Link an already-uploaded study to a service request, called once all files for
    # a study have finished uploading via `upload`/`upload-dicom-external`.
    @extend_schema(request=DicomStudyLinkSpec)
    @action(detail=False, methods=["post"], url_path="link-service-request")
    def link_service_request(self, request):
        request_data = DicomStudyLinkSpec.model_validate(request.data)

        service_request = get_object_or_404(ServiceRequest, external_id=request_data.service_request_id)
        if not AuthorizationController.call("can_write_service_request", request.user, service_request):
            raise PermissionDenied("You do not have permission to update this service request")
        self._authorize_write_radiology_data(service_request.facility)

        record = link_service_request_to_study(service_request, request_data.study_uid)

        return Response(
            {
                "detail": "Service request linked to study successfully",
                "record": record,
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _dedupe_studies(radiology_service_requests):
        return list({r.dicom_study_id: r.dicom_study for r in radiology_service_requests}.values())

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

        return self._dedupe_studies(radiology_service_requests)

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

        return self._dedupe_studies(radiology_service_requests)

    @action(detail=False, methods=["get"], url_path="studies")
    def get_studies(self, request):
        query = DicomStudiesQuerySpec(**request.query_params.dict())

        if query.service_request_id:
            studies = self._studies_for_service_request(query.service_request_id)
        else:
            studies = self._studies_for_encounter(query.encounter_id)

        results = []
        with ThreadPoolExecutor(max_workers=min(10, len(studies) or 1)) as executor:
            future_to_study = {executor.submit(fetch_study, study): study for study in studies}
            for future in as_completed(future_to_study):
                result = future.result()
                if result is not None:
                    results.append(result)

        return Response(results, status=status.HTTP_200_OK)
