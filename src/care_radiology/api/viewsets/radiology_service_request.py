from care.emr.api.viewsets.base import EMRBaseViewSet, EMRRetrieveMixin
from care.security.authorization.base import AuthorizationController
from rest_framework.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema

from care_radiology.api.specs.radiology_service_request import RadiologyServiceRequestReadSpec
from care_radiology.models.radiology_service_request import RadiologyServiceRequest


@extend_schema(tags=["Radiology: Service Request"])
class RadiologyServiceRequestViewSet(EMRRetrieveMixin, EMRBaseViewSet):
    database_model = RadiologyServiceRequest
    pydantic_retrieve_model = RadiologyServiceRequestReadSpec
    lookup_field = "service_request__external_id"

    def authorize_retrieve(self, model_instance):
        service_request = model_instance.service_request
        if not AuthorizationController.call("can_read_service_request", self.request.user, service_request):
            raise PermissionDenied("You do not have permission to view this service request")
        if not AuthorizationController.call("can_read_radiology_data", self.request.user, service_request.facility):
            raise PermissionDenied("You do not have permission to read radiology data for this facility")

    def get_queryset(self):
        return super().get_queryset().select_related("service_request__facility")
