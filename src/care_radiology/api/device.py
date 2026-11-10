from rest_framework.exceptions import ValidationError

from care.emr.models.device import Device
from care.emr.registries.device_type.device_registry import DeviceTypeBase

from care_radiology.api.specs.modality import (
    DicomDeviceMetadataReadSpec,
    DicomDeviceMetadataWriteSpec,
    DicomEnablerMetadataReadSpec,
    DicomEnablerMetadataWriteSpec,
)
from care_radiology.constants import (
    ASSIGNMENT_STATUS_ASSIGNED,
    ASSIGNMENT_STATUS_UNASSIGNED,
    DICOM_CARE_TYPE,
    DICOM_ENABLER_CARE_TYPE,
)
from care_radiology.services.modality_service import (
    AssignmentConflict,
    assignment_status_of,
    is_active_available,
)


def resolve_assignment_status(obj, requested, is_create):
    """
    A new device is always unassigned. On update the requested status is used, or the current one when
    none is sent. As with the external modalities status API, the status the device already has is a 409
    and only an active, available device can be assigned.
    """
    if is_create:
        return ASSIGNMENT_STATUS_UNASSIGNED
    current = assignment_status_of(obj)
    if not requested:
        return current
    if requested == current:
        raise AssignmentConflict(f"Device is already {requested}.")
    if requested == ASSIGNMENT_STATUS_ASSIGNED and not is_active_available(obj):
        raise ValidationError("Device is not active and available.")
    return requested


def write_metadata(obj, validated_data, is_create):
    metadata = validated_data.model_dump(mode="json")
    metadata["assignment_status"] = resolve_assignment_status(obj, validated_data.assignment_status, is_create)
    last_synced_at = obj.metadata.get("last_synced_at")
    if last_synced_at:
        metadata["last_synced_at"] = last_synced_at
    obj.metadata = metadata
    obj.save(update_fields=["metadata"])
    return obj


class ModalityDevice(DeviceTypeBase):
    def _write_metadata(self, request_data, obj, is_create):
        validated_data = DicomDeviceMetadataWriteSpec(**request_data)
        other_dicom_devices = Device.objects.filter(facility_id=obj.facility_id, care_type=DICOM_CARE_TYPE).exclude(
            id=obj.id
        )
        if other_dicom_devices.filter(metadata__machine__ae_title__iexact=validated_data.machine.ae_title).exists():
            raise ValidationError("A modality device with this AE title already exists in the facility")
        enabler = Device.objects.filter(
            facility_id=obj.facility_id,
            care_type=DICOM_ENABLER_CARE_TYPE,
            external_id=validated_data.dicom_enabler,
        ).first()
        if enabler is None:
            raise ValidationError("DICOM Enabler not found in the facility")
        return write_metadata(obj, validated_data, is_create)

    def handle_create(self, request_data, obj):
        return self._write_metadata(request_data, obj, is_create=True)

    def handle_update(self, request_data, obj):
        return self._write_metadata(request_data, obj, is_create=False)

    def list(self, obj):
        return self.retrieve(obj)

    def retrieve(self, obj):
        return DicomDeviceMetadataReadSpec(**obj.metadata).model_dump(mode="json")


class ModalityEnablerDevice(DeviceTypeBase):
    def _write_metadata(self, request_data, obj, is_create):
        validated_data = DicomEnablerMetadataWriteSpec(**request_data)
        return write_metadata(obj, validated_data, is_create)

    def handle_create(self, request_data, obj):
        return self._write_metadata(request_data, obj, is_create=True)

    def handle_update(self, request_data, obj):
        return self._write_metadata(request_data, obj, is_create=False)

    def handle_delete(self, obj):
        if Device.objects.filter(
            facility_id=obj.facility_id,
            care_type=DICOM_CARE_TYPE,
            metadata__dicom_enabler=str(obj.external_id),
        ).exists():
            raise ValidationError("Move or delete the DICOM devices connected to this DICOM Enabler first.")
        return obj

    def list(self, obj):
        return self.retrieve(obj)

    def retrieve(self, obj):
        return DicomEnablerMetadataReadSpec(**obj.metadata).model_dump(mode="json")
