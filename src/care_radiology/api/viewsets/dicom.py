import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.api.viewsets.base import emr_exception_handler
from care.emr.models.patient import Patient
from care.facility.models import Facility
from care.utils.shortcuts import get_object_or_404
from care_radiology.api.specs.dicom import DicomWorklistQuerySpec
from care_radiology.models.imaging_study import ImagingStudy
from care_radiology.security.authentication import (
    StaticAPIKeyAuthentication,
    StaticAPIKeyAuthorization,
)
from care_radiology.services.dicom_service import (
    DicomUploadError,
    WebhookConflictError,
    link_study_to_encounter,
    link_study_to_service_request,
    upload_dicom_file,
)
from care_radiology.services.worklist_service import get_service_requests
from care_radiology.utils.dicom import DicomParseError, parse_date, read_accession_number

logger = logging.getLogger(__name__)


def handle_dicom_upload(patient, dcm_file, service_request=None, encounter=None, user=None):
    try:
        result = upload_dicom_file(patient, dcm_file, user=user)
    except DicomUploadError as e:
        return Response(
            data={"errors": [{"type": "dicom_upload_error", "msg": e.message, **e.extra}]},
            status=e.status_code,
        )

    data = {"message": "DICOM files uploaded to DCM4CHE successfully", **result}

    # The study UID is only known once DCM4CHE has accepted the file, so the link
    # is made here rather than up front.
    if service_request is not None or encounter is not None:
        try:
            if service_request is not None:
                link_study_to_service_request(service_request, result["study_uid"], user=user)
            else:
                link_study_to_encounter(encounter, result["study_uid"], user=user)
        except WebhookConflictError as e:
            # `uploaded` is set because the file is in PACS by this point: without it
            # the caller reads a 409 here as a rejected upload and retries, which the
            # duplicate check then turns into a second, unrelated-looking 409.
            return Response(
                data={
                    "errors": [
                        {
                            "type": "study_link_conflict",
                            "msg": e.message,
                            "uploaded": True,
                            "study_uid": result["study_uid"],
                        }
                    ]
                },
                status=status.HTTP_409_CONFLICT,
            )
        if service_request is not None:
            data["service_request_id"] = str(service_request.external_id)

    return Response(data=data, status=status.HTTP_201_CREATED)


def validate_accession_number(dcm_file, service_request):
    try:
        file_accession_number = read_accession_number(dcm_file)
    except DicomParseError as e:
        return Response(
            data={
                "errors": [
                    {
                        "type": "accession_number_unreadable",
                        "msg": "Could not read the accession number from the DICOM file",
                        "details": e.message,
                    }
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not file_accession_number:
        return Response(
            data={
                "errors": [
                    {
                        "type": "accession_number_missing",
                        "msg": "DICOM file does not contain an accession number",
                    }
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        imaging_study = service_request.imaging_study
    except ImagingStudy.DoesNotExist:
        return Response(
            data={
                "errors": [
                    {
                        "type": "imaging_study_missing",
                        "msg": "Service request has no imaging study to match the accession number against",
                    }
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if file_accession_number != imaging_study.accession_number:
        return Response(
            data={
                "errors": [
                    {
                        "type": "accession_number_mismatch",
                        "msg": "Accession number in the DICOM file does not match the service request",
                    }
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return None


@extend_schema(tags=["Radiology: Dicom"])
class DicomViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

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
        patient_id = request.data.get("patient_id")

        errors = {}
        if not dcm_file:
            errors["file"] = "This value is required"
        if not patient_id:
            errors["patient_id"] = "This value is required"
        if errors:
            raise ValidationError(errors)

        patient = get_object_or_404(Patient, external_id=patient_id)

        return handle_dicom_upload(patient, dcm_file)
