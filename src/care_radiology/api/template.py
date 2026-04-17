from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.models.template import Template
from care_radiology.resources.template.spec import (
    TemplateCreateSpec,
    TemplateListSpec,
)
from care.security.authorization import AuthorizationController


class TemplateViewSet(EMRModelViewSet):
    """CRUD API for saving report templates"""

    database_model = Template
    pydantic_model = TemplateCreateSpec
    pydantic_read_model = TemplateListSpec
    pydantic_update_model = None
    pydantic_retrieve_model = TemplateListSpec

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_date", "modified_date"]

    def authorize_create(self, request_obj):
        # Temporarily allow all users to create templates
        pass

    def authorize_update(self, request_obj, model_instance):
        pass

    def authorize_destroy(self, instance):
        pass

    def get_queryset(self):
        """Return templates belonging to the current user only."""
        qs = super().get_queryset().select_related(
            "modality", "body_part", "scan_protocol", "user"
        )
        user = getattr(self.request, "user", None)
        if user and user.is_authenticated:
            qs = qs.filter(user=user)
        return qs.order_by("-created_date")

    def create(self, request, *args, **kwargs):
        """
        Override create() so that we can pass request.user into Pydantic spec's de_serialize().
        """
        data = request.data.copy()

        # Validate with Pydantic
        spec = self.pydantic_model(**data)

        # Deserialize and inject request.user
        model_instance = spec.de_serialize(user=request.user)
        model_instance.save()

        # Serialize back to response format
        read_spec = self.pydantic_read_model.serialize(model_instance)
        return Response(read_spec.model_dump())
