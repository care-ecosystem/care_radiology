import logging

from django.db.models import Prefetch, Q
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRBaseViewSet, EMRListMixin, EMRRetrieveMixin, EMRUpdateMixin
from care.emr.models.diagnostic_report import DiagnosticReport
from care.emr.models.encounter import Encounter
from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care.emr.resources.service_request.spec import ServiceRequestStatusChoices
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from care_radiology.api.specs.dicom import DicomStudyArchiveSpec, DicomStudyArchiveStateSpec
from care_radiology.api.specs.imaging_study import (
    ImagingStudyReadSpec,
    ImagingStudyRetrieveSpec,
    ImagingStudyUpdateSpec,
)
from care_radiology.api.viewsets.mixins import DicomUploadMixin
from care_radiology.constants import DICOM_FILE_EXTENSIONS
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus
from care_radiology.services.dicom_service import (
    PacsDeleteError,
    archive_study,
    fetch_studies,
    imaging_study_for_encounter,
    imaging_study_for_service_request,
    validate_accession_number,
)
from care_radiology.settings import plugin_settings

logger = logging.getLogger(__name__)


class ImagingStudyFilters(filters.FilterSet):
    encounter = filters.UUIDFilter(field_name="encounter__external_id")


@extend_schema(tags=["Radiology: Imaging Study"])
class ImagingStudyViewSet(DicomUploadMixin, EMRListMixin, EMRRetrieveMixin, EMRUpdateMixin, EMRBaseViewSet):
    database_model = ImagingStudy
    pydantic_read_model = ImagingStudyReadSpec
    pydantic_retrieve_model = ImagingStudyRetrieveSpec
    pydantic_update_model = ImagingStudyUpdateSpec
    lookup_field = "service_request__external_id"
    filterset_class = ImagingStudyFilters
    filter_backends = [filters.DjangoFilterBackend]

    def get_patient(self):
        return get_object_or_404(Patient, external_id=self.kwargs["patient_external_id"])

    def authorize_write_radiology_data(self, facility):
        if not AuthorizationController.call("can_write_radiology_data", self.request.user, facility):
            raise PermissionDenied("You do not have permission to write radiology data for this facility")

    def authorize_retrieve(self, model_instance):
        service_request = model_instance.service_request
        if not AuthorizationController.call("can_read_service_request", self.request.user, service_request):
            raise PermissionDenied("You do not have permission to view this service request")
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, service_request.facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

    def authorize_update(self, request_obj, model_instance):
        self.authorize_retrieve(model_instance)
        self.authorize_write_radiology_data(model_instance.service_request.facility)

    def list(self, request, *args, **kwargs):
        # The PACS details of every study on the page are fetched in one parallel pool.
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(self.filter_queryset(self.get_queryset()), request)
        pacs_details = fetch_studies([study for imaging_study in page for study in imaging_study.studies.all()])
        return paginator.get_paginated_response(
            [ImagingStudyReadSpec.serialize(obj, pacs_details=pacs_details).to_json() for obj in page]
        )

    def get_queryset(self):
        patient = self.get_patient()

        include_archived = False
        if self.action == "retrieve":
            value = self.request.query_params.get("include_archived", "false").lower()
            if value not in ("true", "false"):
                raise ValidationError({"include_archived": "Must be true or false"})
            include_archived = value == "true"
        studies = DicomStudy.objects.select_related("created_by", "updated_by").order_by("-created_date")
        if include_archived:
            studies = studies.select_related("archived_by")
        else:
            studies = studies.filter(is_archived=False)

        queryset = (
            super()
            .get_queryset()
            .filter(Q(service_request__isnull=True) | Q(service_request__deleted=False), patient=patient)
            .select_related("encounter", "service_request__facility")
            .prefetch_related(Prefetch("studies", queryset=studies))
        )
        if self.action != "list":
            return queryset.select_related(
                "service_request__encounter__patient",
                "service_request__activity_definition",
                "service_request__healthcare_service",
            )

        encounter_id = self.request.query_params.get("encounter")
        if not encounter_id:
            raise ValidationError("encounter is required")
        encounter = get_object_or_404(Encounter, external_id=encounter_id, patient=patient)
        if not AuthorizationController.call("can_view_service_request_for_encounter", self.request.user, encounter):
            raise PermissionDenied("You do not have permission to view service requests for this encounter")
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, encounter.facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

        return queryset.filter(
            Q(service_request__isnull=True)
            | Q(
                service_request__status__in=[
                    ServiceRequestStatusChoices.active,
                    ServiceRequestStatusChoices.completed,
                ]
            ),
            encounter=encounter,
        ).prefetch_related(
            Prefetch(
                "service_request__diagnosticreport_set",
                queryset=DiagnosticReport.objects.order_by("-created_date"),
            )
        )

    @action(detail=False, methods=["post"])
    def upload(self, request, *args, **kwargs):
        patient = self.get_patient()
        encounter_id = request.data.get("encounter_id")
        service_request_id = request.data.get("service_request_id")
        dcm_file = request.FILES.get("file")

        errors = {}
        if not encounter_id:
            errors["encounter_id"] = "This value is required"
        if not dcm_file:
            errors["file"] = "This value is required"
        elif not dcm_file.name.lower().endswith(DICOM_FILE_EXTENSIONS):
            errors["file"] = "Only .dcm and .dicom files are supported"
        if errors:
            raise ValidationError(errors)

        encounter = get_object_or_404(
            Encounter.objects.select_related("facility"), external_id=encounter_id, patient=patient
        )

        if not service_request_id:
            self.authorize_write_radiology_data(encounter.facility)
            return self.handle_dicom_upload(imaging_study_for_encounter(encounter), dcm_file, user=request.user)

        service_request = get_object_or_404(
            ServiceRequest.objects.select_related("facility", "imaging_study"),
            external_id=service_request_id,
            patient=patient,
        )
        if service_request.encounter_id != encounter.id:
            raise ValidationError({"service_request_id": "Service request does not belong to this encounter"})
        self.authorize_write_radiology_data(service_request.facility)

        imaging_study = imaging_study_for_service_request(service_request)
        if imaging_study.status == ImagingStudyStatus.CANCELLED:
            raise ValidationError(
                {
                    "errors": [
                        {"type": "imaging_study_cancelled", "msg": "The service request's imaging study is cancelled"}
                    ]
                }
            )

        if plugin_settings.CARE_RADIOLOGY_VALIDATE_ACCESSION_NUMBER:
            validate_accession_number(dcm_file, service_request)
        else:
            logger.warning("DICOM accession number check is disabled on this instance, uploading without it")

        return self.handle_dicom_upload(imaging_study, dcm_file, user=request.user)

    @extend_schema(request=DicomStudyArchiveSpec, responses={200: DicomStudyArchiveStateSpec})
    @action(detail=False, methods=["post"], url_path=r"(?P<study_id>[^/.]+)/archive")
    def archive(self, request, *args, study_id=None, **kwargs):
        study = get_object_or_404(
            DicomStudy.objects.select_related(
                "imaging_study__service_request__facility",
                "imaging_study__encounter__facility",
                "created_by",
            ),
            external_id=study_id,
            imaging_study__patient=self.get_patient(),
            is_archived=False,
        )
        request_data = DicomStudyArchiveSpec(**request.data)
        imaging_study = study.imaging_study
        if imaging_study.service_request:
            self.authorize_write_radiology_data(imaging_study.service_request.facility)
        else:
            self.authorize_write_radiology_data(imaging_study.encounter.facility)

        try:
            archive_study(study, request_data.archive_reason, archived_by=request.user)
        except PacsDeleteError as e:
            return Response(
                data={"errors": [{"type": "pacs_delete_error", "msg": e.message, **e.extra}]},
                status=e.status_code,
            )
        return Response(DicomStudyArchiveStateSpec.serialize(study).to_json(), status=status.HTTP_200_OK)
