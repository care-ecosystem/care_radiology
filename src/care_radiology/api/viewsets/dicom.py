from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.api.viewsets.base import emr_exception_handler
from care.security.authorization import AuthorizationController


@extend_schema(tags=["Radiology: Dicom"])
class DicomViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

    # Called by the nginx proxy's auth_request for every /dicomweb/* request, checks for can_read_radiology_data permission.
    @action(detail=False, methods=["get"], url_path="authenticate")
    def authenticate(self, request):
        if not AuthorizationController.call("can_read_radiology_data", request.user):
            raise PermissionDenied("You do not have permission to read radiology data")
        return Response(status=status.HTTP_200_OK)
