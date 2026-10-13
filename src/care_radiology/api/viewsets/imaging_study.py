from care.emr.api.viewsets.base import EMRBaseViewSet, EMRListMixin, EMRRetrieveMixin, EMRUpdateMixin
from care.emr.models.encounter import Encounter
from care.security.authorization.base import AuthorizationController
from care.utils.shortcuts import get_object_or_404
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError

from care_radiology.api.specs.imaging_study import (
    ImagingStudyReadSpec,
    ImagingStudyRetrieveSpec,
    ImagingStudyUpdateSpec,
)
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.imaging_study import ImagingStudy


@extend_schema(tags=["Radiology: Imaging Study"])
class ImagingStudyViewSet(EMRListMixin, EMRRetrieveMixin, EMRUpdateMixin, EMRBaseViewSet):
    database_model = ImagingStudy
    pydantic_read_model = ImagingStudyReadSpec
    pydantic_retrieve_model = ImagingStudyRetrieveSpec
    pydantic_update_model = ImagingStudyUpdateSpec
    lookup_field = "service_request__external_id"

    def authorize_retrieve(self, model_instance):
        service_request = model_instance.service_request
        if not AuthorizationController.call("can_read_service_request", self.request.user, service_request):
            raise PermissionDenied("You do not have permission to view this service request")
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, service_request.facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

    def authorize_update(self, request_obj, model_instance):
        if not AuthorizationController.call(
            "can_write_radiology_data", self.request.user, model_instance.service_request.facility
        ):
            raise PermissionDenied("You do not have permission to write radiology data for this facility")

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .filter(service_request__deleted=False)
            .select_related("encounter", "service_request__facility")
            .prefetch_related(
                "service_request__diagnosticreport_set",
                Prefetch(
                    "studies",
                    queryset=DicomStudy.objects.filter(dicom_study_uid__isnull=False)
                    .select_related("created_by", "updated_by", "archived_by")
                    .order_by("-created_date"),
                ),
            )
        )
        if self.action != "list":
            return queryset.select_related(
                "service_request__encounter__patient",
                "service_request__activity_definition",
                "service_request__healthcare_service",
            )

        encounter_id = self.request.GET.get("encounter")
        if not encounter_id:
            raise ValidationError("encounter is required")

        encounter = get_object_or_404(Encounter, external_id=encounter_id)
        if not AuthorizationController.call("can_view_service_request_for_encounter", self.request.user, encounter):
            raise PermissionDenied("You do not have permission to view service requests for this encounter")
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, encounter.facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

        return queryset.filter(encounter=encounter)
