import logging

from care.emr.api.viewsets.base import emr_exception_handler
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

from care_radiology.api.specs.dicom import (
    DicomStudyArchiveSpec,
    DicomStudyArchiveStateSpec,
    DicomWorklistQuerySpec,
)
from care_radiology.constants import DICOM_FILE_EXTENSIONS
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.imaging_study import ImagingStudy
from care_radiology.security.authentication import (
    StaticAPIKeyAuthentication,
    StaticAPIKeyAuthorization,
)
from care_radiology.services.dicom_service import (
    DicomUploadError,
    PacsDeleteError,
    WebhookConflictError,
    archive_study,
    ensure_study_linked_to_service_request,
    upload_dicom_file,
)
from care_radiology.services.worklist_service import get_service_requests
from care_radiology.settings import plugin_settings
from care_radiology.utils.dicom import DicomParseError, parse_date, read_accession_number

logger = logging.getLogger(__name__)


@extend_schema(tags=["Radiology: Dicom"])
class DicomViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

    def _authorize_write_radiology_data(self, facility):
        if not AuthorizationController.call("can_write_radiology_data", self.request.user, facility):
            raise PermissionDenied("You do not have permission to write radiology data for this facility")

    def _resolve_facility_for_archive(self, study):
        if not (study.imaging_study and study.imaging_study.service_request):
            raise ValidationError({"detail": "Cannot archive a study that is not linked to a service request"})
        return study.imaging_study.service_request.facility

    def _handle_dicom_upload(self, patient, dcm_file, service_request=None, user=None):
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
        if service_request is not None:
            try:
                ensure_study_linked_to_service_request(service_request, result["study_uid"], user=user)
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
            data["service_request_id"] = str(service_request.external_id)

        return Response(data=data, status=status.HTTP_201_CREATED)

    def _validate_accession_number(self, dcm_file, service_request):
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

        expected_accession_number = (
            ImagingStudy.objects.filter(service_request=service_request)
            .values_list("accession_number", flat=True)
            .first()
        )
        if file_accession_number != expected_accession_number:
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
        patient_id = request.data.get("patient_id")
        service_request_id = request.data.get("service_request_id")
        dcm_file = request.FILES.get("file")

        errors = {}
        if not patient_id:
            errors["patient_id"] = "This value is required"
        if not service_request_id:
            errors["service_request_id"] = "This value is required"
        if not dcm_file:
            errors["file"] = "This value is required"
        elif not dcm_file.name.lower().endswith(DICOM_FILE_EXTENSIONS):
            errors["file"] = "Only .dcm and .dicom files are supported"
        if errors:
            raise ValidationError(errors)

        patient = get_object_or_404(Patient, external_id=patient_id)
        service_request = get_object_or_404(ServiceRequest, external_id=service_request_id)

        if service_request.patient_id != patient.id:
            raise ValidationError({"service_request_id": "Service request does not belong to this patient"})

        self._authorize_write_radiology_data(service_request.facility)

        if plugin_settings.CARE_RADIOLOGY_VALIDATE_ACCESSION_NUMBER:
            error_response = self._validate_accession_number(dcm_file, service_request)
            if error_response is not None:
                return error_response
        else:
            logger.warning("DICOM accession number check is disabled on this instance, uploading without it")

        return self._handle_dicom_upload(patient, dcm_file, service_request=service_request, user=request.user)

    # DCM Files upload via static API key (no user auth required)
    @action(
        detail=False,
        methods=["post"],
        authentication_classes=[StaticAPIKeyAuthentication],
        permission_classes=[StaticAPIKeyAuthorization],
    )
    def upload_dicom_external(self, request):
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

        try:
            accession_number = read_accession_number(dcm_file)
        except DicomParseError as e:
            logger.warning("Could not read the accession number from an external DICOM upload: %s", e.message)
            accession_number = None

        imaging_study = None
        if accession_number:
            imaging_study = (
                ImagingStudy.objects.filter(
                    accession_number=accession_number,
                    service_request__patient=patient,
                    service_request__deleted=False,
                )
                .select_related("service_request")
                .order_by("-created_date")
                .first()
            )
        service_request = imaging_study.service_request if imaging_study else None

        return self._handle_dicom_upload(patient, dcm_file, service_request=service_request)

    @extend_schema(request=DicomStudyArchiveSpec, responses={200: DicomStudyArchiveStateSpec})
    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        study = get_object_or_404(
            DicomStudy.objects.select_related(
                "imaging_study__service_request__facility", "created_by", "updated_by"
            ),
            external_id=pk,
        )
        request_data = DicomStudyArchiveSpec(**request.data)
        facility = self._resolve_facility_for_archive(study)
        self._authorize_write_radiology_data(facility)

        try:
            archive_study(study, request_data.archive_reason, archived_by=request.user)
        except PacsDeleteError as e:
            return Response(
                data={"errors": [{"type": "pacs_delete_error", "msg": e.message, **e.extra}]},
                status=e.status_code,
            )
        return Response(DicomStudyArchiveStateSpec.serialize(study).to_json(), status=status.HTTP_200_OK)
