from care_radiology.models.scan_protocol import ScanProtocol
from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.resources.scan_protocol.spec import (
    ScanProtocolListSpec,
    ScanProtocolCreateSpec,
    ScanProtocolUpdateSpec,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from care.security.authorization import AuthorizationController
from rest_framework.exceptions import PermissionDenied


class ScanProtocolViewSet(EMRModelViewSet):
    """CRUD API for ScanProtocol"""

    database_model = ScanProtocol
    pydantic_model = ScanProtocolCreateSpec
    pydantic_read_model = ScanProtocolListSpec
    pydantic_update_model = ScanProtocolUpdateSpec
    pydantic_retrieve_model = ScanProtocolListSpec

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]
    search_fields = [
        "display_name",
        "modality__display_name",
        "body_part__display_name",
    ]

    def authorize_create(self, request_obj):
        pass

    def authorize_update(self, request_obj, model_instance):
        pass

    def authorize_destroy(self, instance):
        pass

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("modality", "body_part")
            .order_by("-created_date")
        )
