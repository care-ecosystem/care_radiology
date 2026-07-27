from django_filters import rest_framework as filters
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter

from care.emr.api.viewsets.base import (
    EMRBaseViewSet,
    EMRCreateMixin,
    EMRListMixin,
    EMRRetrieveMixin,
    EMRUpdateMixin,
)
from care.security.authorization import AuthorizationController

from care_radiology.models.observation_template import ObservationTemplate
from care_radiology.resources.observation_template.spec import (
    ObservationTemplateCreateSpec,
    ObservationTemplateReadSpec,
    ObservationTemplateUpdateSpec,
)


class ObservationTemplateFilters(filters.FilterSet):
    observation_definition = filters.UUIDFilter(
        field_name="observation_definition__external_id"
    )
    activity_definition = filters.UUIDFilter(
        field_name="activity_definition__external_id"
    )
    title = filters.CharFilter(lookup_expr="icontains")


class ObservationTemplateViewSet(
    EMRCreateMixin,
    EMRRetrieveMixin,
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
        if not AuthorizationController.call(
            "can_write_radiology_report", self.request.user
        ):
            raise PermissionDenied(
                "You do not have permission to create templates"
            )

    def authorize_update(self, request_obj, model_instance):
        if not AuthorizationController.call(
            "can_write_radiology_report", self.request.user
        ):
            raise PermissionDenied(
                "You do not have permission to update templates"
            )

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
        if not AuthorizationController.call(
            "can_read_radiology_report", self.request.user
        ):
            raise PermissionDenied(
                "You do not have permission to read templates"
            )

        facility = self.request.query_params.get("facility")
        if not facility:
            raise ValidationError({"facility": "This value is required"})

        qs = qs.filter(facility__external_id=facility)
        return qs.order_by("-created_date")
