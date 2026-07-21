from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter

from care.emr.api.viewsets.base import EMRModelViewSet

from care_radiology.models.observation_template import ObservationTemplate
from care_radiology.resources.observation_template.spec import (
    ObservationTemplateCreateSpec,
    ObservationTemplateReadSpec,
    ObservationTemplateUpdateSpec,
)


class ObservationTemplateFilters(filters.FilterSet):
    facility = filters.UUIDFilter(field_name="facility__external_id")
    observation_definition = filters.UUIDFilter(
        field_name="observation_definition__external_id"
    )
    activity_definition = filters.UUIDFilter(
        field_name="activity_definition__external_id"
    )
    title = filters.CharFilter(lookup_expr="icontains")


class ObservationTemplateViewSet(EMRModelViewSet):
    """CRUD API for saving observation templates"""

    database_model = ObservationTemplate
    pydantic_model = ObservationTemplateCreateSpec
    pydantic_update_model = ObservationTemplateUpdateSpec
    pydantic_read_model = ObservationTemplateReadSpec
    filterset_class = ObservationTemplateFilters
    filter_backends = [filters.DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]

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
        )
        if self.action == "list":
            facility = self.request.query_params.get("facility")
            if not facility:
                raise ValidationError({"facility": "This query parameter is required"})
            qs = qs.filter(facility__external_id=facility)
        return qs.order_by("-created_date")
