from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.api.viewsets.base import emr_exception_handler
from care.facility.models import Facility
from care.utils.pagination.care_pagination import CareLimitOffsetPagination
from care.utils.shortcuts import get_object_or_404
from care_radiology.api.specs.external import DicomWorklistQuerySpec, WebhookMppsSpec
from care_radiology.api.viewsets.mixins import DicomUploadMixin
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.security.authentication import (
    StaticAPIKeyAuthentication,
    StaticAPIKeyAuthorization,
)
from care_radiology.services.dicom_service import (
    imaging_study_for_accession_number,
    process_mpps_webhook,
    read_file_accession_number,
)
from care_radiology.services.worklist_service import get_service_requests, worklist_entries
from care_radiology.utils.dicom import parse_date


@extend_schema(tags=["Radiology: External"])
class FacilityExternalViewSet(DicomUploadMixin, ViewSet):
    authentication_classes = [StaticAPIKeyAuthentication]
    permission_classes = [StaticAPIKeyAuthorization]

    def get_exception_handler(self):
        return emr_exception_handler

    def get_facility(self):
        return get_object_or_404(Facility, external_id=self.kwargs["facility_external_id"])

    @action(detail=False, methods=["get"])
    def worklist(self, request, *args, **kwargs):
        facility = self.get_facility()
        query = DicomWorklistQuerySpec(**request.query_params.dict())

        service_requests = get_service_requests(
            modality=query.modality,
            from_date=parse_date(query.created_date_after),
            to_date=parse_date(query.created_date_before),
            facility=facility,
        )
        paginator = CareLimitOffsetPagination()
        page = paginator.paginate_queryset(service_requests, request, view=self)
        return Response(
            data={
                "count": paginator.count,
                "status": "success",
                "results": worklist_entries(page, modality=query.modality),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="imaging_study/upload")
    def upload(self, request, *args, **kwargs):
        facility = self.get_facility()
        dcm_file = request.FILES.get("file")
        if not dcm_file:
            raise ValidationError({"file": "This value is required"})

        # The file is linked by its accession number, so one that cannot be linked is
        # rejected before it reaches the PACS.
        accession_number = read_file_accession_number(dcm_file)
        imaging_study = imaging_study_for_accession_number(accession_number, facility)
        return self.handle_dicom_upload(imaging_study, dcm_file)

    # MPPS status update, mapped to a ServiceRequest tag.
    @extend_schema(request=WebhookMppsSpec)
    @action(detail=False, methods=["patch"], url_path="imaging_study/status")
    def update_status(self, request, *args, **kwargs):
        facility = self.get_facility()
        request_data = WebhookMppsSpec.model_validate(request.data)
        RadiologyWebhookLogs.objects.create(raw_data=request.data, type="MPPS")

        record = process_mpps_webhook(facility, request_data.service_request_id, request_data.study_status)
        return Response(record, status=status.HTTP_200_OK)
