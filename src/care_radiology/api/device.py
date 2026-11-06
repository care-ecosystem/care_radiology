from rest_framework.exceptions import ValidationError

from care.emr.models.device import Device
from care.emr.registries.device_type.device_registry import DeviceTypeBase

from care_radiology.api.specs.modality import (
    DicomDeviceMetadataReadSpec,
    DicomDeviceMetadataWriteSpec,
    DicomEnablerMetadataReadSpec,
    DicomEnablerMetadataWriteSpec,
)
from care_radiology.constants import DICOM_CARE_TYPE, DICOM_ENABLER_CARE_TYPE
from care_radiology.services.modality_service import assignment_status_of


def write_metadata(obj, validated_data):
    metadata = validated_data.model_dump(mode="json")
    # assignment_status is changed only by the external modalities status API: a new device is written as
    # unassigned and an edited one keeps the value it has.
    metadata["assignment_status"] = assignment_status_of(obj)
    obj.metadata = metadata
    obj.save(update_fields=["metadata"])
    return obj


class ModalityDevice(DeviceTypeBase):
    def _write_metadata(self, request_data, obj):
        validated_data = DicomDeviceMetadataWriteSpec(**request_data)
        other_dicom_devices = Device.objects.filter(facility_id=obj.facility_id, care_type=DICOM_CARE_TYPE).exclude(
            id=obj.id
        )
        if other_dicom_devices.filter(metadata__machine__ae_title__iexact=validated_data.machine.ae_title).exists():
            raise ValidationError("A modality device with this AE title already exists in the facility")
        scheduled_station_ae_title = validated_data.machine.scheduled_station_ae_title
        if (
            scheduled_station_ae_title
            and other_dicom_devices.filter(
                metadata__machine__scheduled_station_ae_title__iexact=scheduled_station_ae_title
            ).exists()
        ):
            raise ValidationError("A DICOM device with this scheduled station AE title already exists in the facility")
        if not Device.objects.filter(
            facility_id=obj.facility_id,
            care_type=DICOM_ENABLER_CARE_TYPE,
            external_id=validated_data.dicom_enabler,
        ).exists():
            raise ValidationError("DICOM Enabler not found in the facility")
        return write_metadata(obj, validated_data)

    def handle_create(self, request_data, obj):
        return self._write_metadata(request_data, obj)

    def handle_update(self, request_data, obj):
        return self._write_metadata(request_data, obj)

    def list(self, obj):
        return self.retrieve(obj)

    def retrieve(self, obj):
        return DicomDeviceMetadataReadSpec(**obj.metadata).model_dump(mode="json")


class ModalityEnablerDevice(DeviceTypeBase):
    def _write_metadata(self, request_data, obj):
        return write_metadata(obj, DicomEnablerMetadataWriteSpec(**request_data))

    def handle_create(self, request_data, obj):
        return self._write_metadata(request_data, obj)

    def handle_update(self, request_data, obj):
        return self._write_metadata(request_data, obj)

    def list(self, obj):
        return self.retrieve(obj)

    def retrieve(self, obj):
        return DicomEnablerMetadataReadSpec(**obj.metadata).model_dump(mode="json")
