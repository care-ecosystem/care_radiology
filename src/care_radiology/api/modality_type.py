from care_radiology.models.modality_type import ModalityType
from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.resources.modality_type.spec import (
    ModalityTypeListSpec,
    ModalityTypeCreateSpec,
    ModalityTypeUpdateSpec,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from care.security.authorization import AuthorizationController
from rest_framework.exceptions import PermissionDenied


class ModalityTypeViewSet(EMRModelViewSet):
    database_model = ModalityType
    pydantic_read_model = ModalityTypeListSpec
    pydantic_model = ModalityTypeCreateSpec
    pydantic_update_model = ModalityTypeUpdateSpec
    pydantic_retrieve_model = ModalityTypeListSpec

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]
    search_fields = ["display_name"]

    def authorize_create(self, request_obj):
        pass

    def authorize_update(self, request_obj, model_instance):
        pass

    def authorize_destroy(self, instance):
        pass

    def get_queryset(self):
        return super().get_queryset().order_by("-created_date")
