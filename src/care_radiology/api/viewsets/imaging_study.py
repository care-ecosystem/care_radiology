from django.db.models import Prefetch, Q
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError

from care.emr.api.viewsets.base import EMRBaseViewSet, EMRListMixin, EMRRetrieveMixin, EMRUpdateMixin
from care.emr.models.diagnostic_report import DiagnosticReport
from care.emr.models.encounter import Encounter
from care.emr.models.patient import Patient
from care.emr.resources.service_request.spec import ServiceRequestStatusChoices
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from care_radiology.api.specs.imaging_study import (
    ImagingStudyReadSpec,
    ImagingStudyRetrieveSpec,
    ImagingStudyUpdateSpec,
)
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.imaging_study import ImagingStudy
from care_radiology.services.dicom_service import fetch_studies


class ImagingStudyFilters(filters.FilterSet):
    encounter = filters.UUIDFilter(field_name="encounter__external_id")


@extend_schema(tags=["Radiology: Imaging Study"])
class ImagingStudyViewSet(EMRListMixin, EMRRetrieveMixin, EMRUpdateMixin, EMRBaseViewSet):
    database_model = ImagingStudy
    pydantic_read_model = ImagingStudyReadSpec
    pydantic_retrieve_model = ImagingStudyRetrieveSpec
    pydantic_update_model = ImagingStudyUpdateSpec
    lookup_field = "service_request__external_id"
    filterset_class = ImagingStudyFilters
    filter_backends = [filters.DjangoFilterBackend]

    def authorize_retrieve(self, model_instance):
        service_request = model_instance.service_request
        if not AuthorizationController.call("can_read_service_request", self.request.user, service_request):
            raise PermissionDenied("You do not have permission to view this service request")
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, service_request.facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

    def authorize_update(self, request_obj, model_instance):
        self.authorize_retrieve(model_instance)
        if not AuthorizationController.call(
            "can_write_radiology_data", self.request.user, model_instance.service_request.facility
        ):
            raise PermissionDenied("You do not have permission to write radiology data for this facility")

    def list(self, request, *args, **kwargs):
        # The PACS details of every study on the page are fetched in one parallel pool.
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(self.filter_queryset(self.get_queryset()), request)
        pacs_details = fetch_studies([study for imaging_study in page for study in imaging_study.studies.all()])
        return paginator.get_paginated_response(
            [ImagingStudyReadSpec.serialize(obj, pacs_details=pacs_details).to_json() for obj in page]
        )

    def get_queryset(self):
        patient = get_object_or_404(Patient, external_id=self.kwargs["patient_external_id"])

        include_archived = False
        if self.action == "retrieve":
            value = self.request.query_params.get("include_archived", "false").lower()
            if value not in ("true", "false"):
                raise ValidationError({"include_archived": "Must be true or false"})
            include_archived = value == "true"
        studies = DicomStudy.objects.order_by("-created_date")
        if not include_archived:
            studies = studies.filter(is_archived=False)

        queryset = (
            super()
            .get_queryset()
            .filter(Q(service_request__isnull=True) | Q(service_request__deleted=False), encounter__patient=patient)
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
