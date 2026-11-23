from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.api.viewsets.base import emr_exception_handler
from care.emr.models.device import Device
from care.facility.models import Facility
from care.security.authorization import AuthorizationController
from care.utils.pagination.care_pagination import CareLimitOffsetPagination
from care.utils.shortcuts import get_object_or_404
from care_radiology.api.specs.external import DicomWorklistQuerySpec, WebhookMppsSpec
from care_radiology.api.specs.modality import ModalityAssignmentStatusUpdateSpec, ModalityListQuerySpec
from care_radiology.api.viewsets.mixins import DicomUploadMixin
from care_radiology.constants import DICOM_CARE_TYPE, DICOM_ENABLER_CARE_TYPE
from care_radiology.models.webhook_logs import RadiologyWebhookLogs
from care_radiology.security.authentication import ServiceAccountTokenAuthentication
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
    authentication_classes = [ServiceAccountTokenAuthentication]

    def get_exception_handler(self):
        return emr_exception_handler

    def get_facility(self):
        return get_object_or_404(Facility, external_id=self.kwargs["facility_external_id"])

    def authorize_read_worklist(self, facility):
        if not AuthorizationController.call("can_read_dicom_worklist", self.request.user, facility):
            raise PermissionDenied("You do not have permission to read worklist for this facility")

    def authorize_upload_dicom_study(self, facility):
        if not AuthorizationController.call("can_write_upload_dicom_study", self.request.user, facility):
            raise PermissionDenied("You do not have permission to upload DICOM studies for this facility")

    @action(detail=False, methods=["get"])
    def worklist(self, request, *args, **kwargs):
        facility = self.get_facility()
        self.authorize_read_worklist(facility)
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
        devices = AuthorizationController.call("get_accessible_radiology_devices", devices, request.user, facility)
        paginator = CareLimitOffsetPagination()
        page = paginator.paginate_queryset(devices, request, view=self)
        return paginator.get_paginated_response(modality_list_items(page))

    # One unassigned DICOM Enabler or DICOM device, with a DICOM Enabler's DICOM endpoints.
    @action(detail=False, methods=["get"], url_path=r"modalities/(?P<device_id>[^/.]+)", url_name="modality-detail")
    def retrieve_modality(self, request, device_id, *args, **kwargs):
        device = get_modality(facility=self.get_facility(), device_id=device_id)
        if not AuthorizationController.call("can_read_device", request.user, device):
            raise PermissionDenied("You do not have permission to read this device")
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
        device = get_object_or_404(
            Device,
            facility=facility,
            care_type__in=[DICOM_ENABLER_CARE_TYPE, DICOM_CARE_TYPE],
            external_id=device_id,
        )
        if not AuthorizationController.call("can_write_dicom_status", request.user, facility, device):
            raise PermissionDenied("You do not have permission to update the status of this device")
        request_data = ModalityAssignmentStatusUpdateSpec.model_validate(request.data)
        device = update_modality_assignment_status(
            facility=facility,
            device_id=device_id,
            assignment_status=request_data.assignment_status,
            user=request.user,
        )
        return Response(modality_detail(device), status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="imaging_study/upload")
    def upload(self, request, *args, **kwargs):
        facility = self.get_facility()
        self.authorize_upload_dicom_study(facility)
        dcm_file = request.FILES.get("file")
        if not dcm_file:
            raise ValidationError({"file": "This value is required"})

        # The file is linked by its accession number, so one that cannot be linked is
        # rejected before it reaches the PACS.
        accession_number = read_file_accession_number(dcm_file)
        imaging_study = imaging_study_for_accession_number(accession_number, facility)
        return self.handle_dicom_upload(imaging_study, dcm_file, user=request.user)

    # MPPS status update, mapped to an imaging study status and, optionally, a ServiceRequest tag.
    @extend_schema(request=WebhookMppsSpec)
    @action(detail=False, methods=["patch"], url_path="imaging_study/status")
    def update_status(self, request, *args, **kwargs):
        facility = self.get_facility()
        if not AuthorizationController.call("can_write_dicom_status", request.user, facility):
            raise PermissionDenied("You do not have permission to update imaging study status for this facility")
        request_data = WebhookMppsSpec.model_validate(request.data)
        RadiologyWebhookLogs.objects.create(
            raw_data=request.data, type="MPPS", created_by=request.user, updated_by=request.user
        )

        record = process_mpps_webhook(
            facility, request_data.service_request_id, request_data.study_status, user=request.user
        )
        return Response(record, status=status.HTTP_200_OK)
