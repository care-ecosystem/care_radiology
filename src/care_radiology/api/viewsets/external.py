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
from care_radiology.api.specs.modality import ModalityAssignmentStatusUpdateSpec, ModalityListQuerySpec
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
from care_radiology.services.modality_service import (
    get_modalities,
    get_modality,
    modality_detail,
    modality_list_items,
    update_modality_assignment_status,
)
from care_radiology.services.worklist_service import get_service_requests, worklist_devices, worklist_entries


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

        devices = worklist_devices(facility, query.device_id)
        location_ids = {device.current_location_id for device in devices} if query.device_id is not None else None
        service_requests = get_service_requests(
            location_ids=location_ids,
            from_date=query.created_date_after,
            to_date=query.created_date_before,
            facility=facility,
        )
        paginator = CareLimitOffsetPagination()
        page = paginator.paginate_queryset(service_requests, request, view=self)
        return Response(
            data={
                "count": paginator.count,
                "status": "success",
                "results": worklist_entries(page, devices, location_ids),
            },
            status=status.HTTP_200_OK,
        )

    # The facility's DICOM Enablers and DICOM devices, for the DICOM Enabler to pick from.
    @action(detail=False, methods=["get"])
    def modalities(self, request, *args, **kwargs):
        facility = self.get_facility()
        query = ModalityListQuerySpec(**request.query_params.dict())

        devices = get_modalities(
            facility=facility,
            care_type=query.care_type,
            assignment_status=query.assignment_status,
            dicom_enabler=query.device_id,
            device_name=query.device_name,
        )
        paginator = CareLimitOffsetPagination()
        page = paginator.paginate_queryset(devices, request, view=self)
        return paginator.get_paginated_response(modality_list_items(page))

    # One unassigned DICOM Enabler or DICOM device, with a DICOM Enabler's DICOM endpoints.
    @action(detail=False, methods=["get"], url_path=r"modalities/(?P<device_id>[^/.]+)", url_name="modality-detail")
    def retrieve_modality(self, request, device_id, *args, **kwargs):
        device = get_modality(facility=self.get_facility(), device_id=device_id)
        return Response(modality_detail(device), status=status.HTTP_200_OK)

    # Assigns a DICOM Enabler or DICOM device once it is picked in the Modality Emulator, or unassigns it.
    @extend_schema(request=ModalityAssignmentStatusUpdateSpec)
    @action(
        detail=False,
        methods=["patch"],
        url_path=r"modalities/(?P<device_id>[^/.]+)/status",
        url_name="modality-status",
    )
    def update_modality_status(self, request, device_id, *args, **kwargs):
        facility = self.get_facility()
        request_data = ModalityAssignmentStatusUpdateSpec.model_validate(request.data)
        device = update_modality_assignment_status(
            facility=facility,
            device_id=device_id,
            assignment_status=request_data.assignment_status,
        )
        return Response(modality_detail(device), status=status.HTTP_200_OK)

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

    # MPPS status update, mapped to an imaging study status and, optionally, a ServiceRequest tag.
    @extend_schema(request=WebhookMppsSpec)
    @action(detail=False, methods=["patch"], url_path="imaging_study/status")
    def update_status(self, request, *args, **kwargs):
        facility = self.get_facility()
        request_data = WebhookMppsSpec.model_validate(request.data)
        RadiologyWebhookLogs.objects.create(raw_data=request.data, type="MPPS")

        record = process_mpps_webhook(facility, request_data.service_request_id, request_data.study_status)
        return Response(record, status=status.HTTP_200_OK)
