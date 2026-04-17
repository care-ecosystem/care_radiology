from care_radiology.models.body_part import BodyPart
from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.resources.body_part.spec import (
    BodyPartListSpec,
    BodyPartCreateSpec,
    BodyPartUpdateSpec,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from care.security.authorization import AuthorizationController
from rest_framework.exceptions import PermissionDenied


class BodyPartViewSet(EMRModelViewSet):
    """CRUD API for BodyPart"""

    database_model = BodyPart
    pydantic_model = BodyPartCreateSpec
    pydantic_read_model = BodyPartListSpec
    pydantic_update_model = BodyPartUpdateSpec
    pydantic_retrieve_model = BodyPartListSpec

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]
    search_fields = ["display_name", "modality__display_name"]

    def authorize_create(self, request_obj):
        pass

    def authorize_update(self, request_obj, model_instance):
        pass

    def authorize_destroy(self, instance):
        pass

    def get_queryset(self):
        return super().get_queryset().select_related("modality").order_by("-created_date")
