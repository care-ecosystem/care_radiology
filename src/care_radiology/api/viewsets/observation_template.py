from django.db import IntegrityError
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter

from care.emr.api.viewsets.base import (
    EMRBaseViewSet,
    EMRCreateMixin,
    EMRListMixin,
    EMRUpdateMixin,
)
from care.facility.models import Facility
from care.security.authorization import AuthorizationController
from care_radiology.api.specs.observation_template import (
    ObservationTemplateCreateSpec,
    ObservationTemplateReadSpec,
    ObservationTemplateUpdateSpec,
)
from care_radiology.models.observation_template import ObservationTemplate


class ObservationTemplateFilters(filters.FilterSet):
    observation_definition = filters.UUIDFilter(field_name="observation_definition__external_id")
    activity_definition = filters.UUIDFilter(field_name="activity_definition__external_id")
    title = filters.CharFilter(lookup_expr="icontains")
    created_by = filters.UUIDFilter(field_name="created_by__external_id")


@extend_schema(tags=["Radiology: Observation Result Template"])
class ObservationTemplateViewSet(
    EMRCreateMixin,
    EMRUpdateMixin,
    EMRListMixin,
    EMRBaseViewSet,
):
    """CRUD API for saving observation templates"""

    database_model = ObservationTemplate
    pydantic_model = ObservationTemplateCreateSpec
    pydantic_update_model = ObservationTemplateUpdateSpec
    pydantic_read_model = ObservationTemplateReadSpec
    filterset_class = ObservationTemplateFilters
    filter_backends = [filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]

    def authorize_create(self, request_obj):
        facility = Facility.objects.get(external_id=request_obj.facility)
        if not AuthorizationController.call(
            "can_write_radiology_observation_result_template", self.request.user, facility=facility
        ):
            raise PermissionDenied("You do not have permission to create templates for this facility")

    def authorize_update(self, request_obj, model_instance):
        if not AuthorizationController.call(
            "can_write_radiology_observation_result_template",
            self.request.user,
            facility=model_instance.facility,
        ):
            raise PermissionDenied("You do not have permission to update templates for this facility")

    def perform_update(self, instance):
        try:
            super().perform_update(instance)
        except IntegrityError as e:
            raise ValidationError({"title": "A template with this title already exists for this facility"}) from e

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related(
                "facility",
                "observation_definition",
                "activity_definition",
            )
            .prefetch_related("data")
            .order_by("-created_date")
        )
        if self.action != "list":
            return qs

        facility = self.request.query_params.get("facility")
        if not facility:
            raise ValidationError({"facility": "This value is required"})

        facility_obj = Facility.objects.filter(external_id=facility).first()
        if not facility_obj or not AuthorizationController.call(
            "can_read_radiology_observation_result_template", self.request.user, facility=facility_obj
        ):
            raise PermissionDenied("You do not have permission to read templates for this facility")

        return qs.filter(facility=facility_obj)
