from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.api.viewsets.base import emr_exception_handler


@extend_schema(tags=["Radiology: Dicom"])
class DicomViewSet(ViewSet):
    def get_exception_handler(self):
        return emr_exception_handler

    # A dummy API for JWT verification called by nginx-proxy for dicomweb requests
    @action(detail=False, methods=["get"], url_path="authenticate")
    def authenticate(self, _):
        return Response(status=status.HTTP_200_OK)
