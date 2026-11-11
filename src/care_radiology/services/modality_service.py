import uuid

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from care.emr.models.device import Device
from care.emr.resources.device.spec import DeviceAvailabilityStatusChoices, DeviceStatusChoices
from care.utils.shortcuts import get_object_or_404
from care_radiology.constants import (
    ASSIGNMENT_STATUS_ASSIGNED,
    ASSIGNMENT_STATUS_UNASSIGNED,
    DICOM_CARE_TYPE,
    DICOM_ENABLER_CARE_TYPE,
)


class AssignmentConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


def is_active_available(device):
    return (
        device.status == DeviceStatusChoices.active
        and device.availability_status == DeviceAvailabilityStatusChoices.available
    )


def assignment_status_of(device):
    return device.metadata.get("assignment_status") or ASSIGNMENT_STATUS_UNASSIGNED


def active_available_devices(facility):
    return Device.objects.filter(
        facility=facility,
        status=DeviceStatusChoices.active,
        availability_status=DeviceAvailabilityStatusChoices.available,
    )


def dicom_enabler_id(facility, value, field):
    """
    `value` as the external_id of an active, available DICOM Enabler of the facility, or a 400 naming the query
    parameter `field`.
    """
    try:
        enabler_id = uuid.UUID(value)
    except ValueError:
        raise ValidationError({field: "Must be a valid DICOM Enabler id."}) from None
    enabler = Device.objects.filter(
        facility=facility, care_type=DICOM_ENABLER_CARE_TYPE, external_id=enabler_id
    ).first()
    if enabler is None:
        raise ValidationError({field: "No DICOM Enabler with this id in the facility."})
    if not is_active_available(enabler):
        raise ValidationError({field: "Device is not active and available."})
    return enabler_id


def get_modalities(*, facility, care_type=None, assignment_status=None, dicom_enabler=None, device_name=None):
    """
    The facility's active, available DICOM Enablers and DICOM devices, narrowed by the filters given.
    `dicom_enabler` gives only the DICOM devices connected to that DICOM Enabler, not the enabler itself.
    `device_name` matches any part of the device name, ignoring case.
    """
    filters = Q(care_type__in=[DICOM_ENABLER_CARE_TYPE, DICOM_CARE_TYPE])

    if care_type:
        filters &= Q(care_type=care_type)

    if device_name:
        filters &= Q(registered_name__icontains=device_name)

    # A device whose metadata has no assignment_status has never been assigned.
    if assignment_status == ASSIGNMENT_STATUS_ASSIGNED:
        filters &= Q(metadata__assignment_status=ASSIGNMENT_STATUS_ASSIGNED)
    elif assignment_status == ASSIGNMENT_STATUS_UNASSIGNED:
        # Not a negated match on "assigned": for a missing key that is NULL in SQL and drops the row.
        filters &= Q(metadata__assignment_status=ASSIGNMENT_STATUS_UNASSIGNED) | ~Q(
            metadata__has_key="assignment_status"
        )

    if dicom_enabler is not None:
        enabler_id = dicom_enabler_id(facility, dicom_enabler, field="device_id")
        filters &= Q(care_type=DICOM_CARE_TYPE, metadata__dicom_enabler=str(enabler_id))

    return (
        active_available_devices(facility)
        .filter(filters)
        .select_related("current_location")
        .order_by("care_type", "registered_name", "id")
    )


def get_modality(*, facility, device_id):
    """
    One active, available DICOM Enabler or DICOM device of the facility, assigned or not, or a 400 naming
    `device_id` that says why it cannot be retrieved.
    """
    try:
        device_uuid = uuid.UUID(device_id)
    except ValueError:
        raise ValidationError({"device_id": "Must be a valid device id."}) from None
    device = (
        Device.objects.filter(
            facility=facility,
            care_type__in=[DICOM_ENABLER_CARE_TYPE, DICOM_CARE_TYPE],
            external_id=device_uuid,
        )
        .select_related("current_location")
        .first()
    )
    if device is None:
        raise ValidationError({"device_id": "No DICOM Enabler or DICOM device with this id in the facility."})
    if not is_active_available(device):
        raise ValidationError({"device_id": "Device is not active and available."})
    return device


def update_modality_assignment_status(*, facility, device_id, assignment_status):
    """
    Sets the assignment_status of a DICOM Enabler or DICOM device of the facility. A 404 when it is not
    one; a 400 when assigning a device that is not active and available. Every call through here also sets
    last_synced_at to now, including one that sends the status the device already has.
    """
    with transaction.atomic():
        device = get_object_or_404(
            Device.objects.select_for_update(of=("self",)).select_related("current_location"),
            facility=facility,
            care_type__in=[DICOM_ENABLER_CARE_TYPE, DICOM_CARE_TYPE],
            external_id=device_id,
        )
        if assignment_status == ASSIGNMENT_STATUS_ASSIGNED and not is_active_available(device):
            raise ValidationError({"device_id": "Device is not active and available."})
        device.metadata = {
            **device.metadata,
            "assignment_status": assignment_status,
            "last_synced_at": timezone.now().isoformat(),
        }
        device.save(update_fields=["metadata"])
    return device


def modality_list_items(devices):
    return [modality_list_item(device) for device in devices]


def modality_list_item(device):
    metadata = device.metadata
    location = device.current_location
    item = {
        "id": str(device.external_id),
        "device_name": device.registered_name,
        "device_type": device.care_type,
        "location": {"id": str(location.external_id), "name": location.name} if location else None,
        "device_status": {
            "status": device.status,
            "availability_status": device.availability_status,
        },
        "assignment_status": assignment_status_of(device),
        "last_synced_at": metadata.get("last_synced_at"),
    }
    # The fields of the other device type are left out, not returned as null.
    if device.care_type == DICOM_CARE_TYPE:
        machine = metadata.get("machine") or {}
        item["machine"] = {
            "ae_title": machine.get("ae_title"),
            "modality": machine.get("modality"),
            "ip": machine.get("ip"),
        }
        item["dicom_enabler"] = metadata.get("dicom_enabler")
    else:
        item["ip"] = metadata.get("ip")
    return item


def modality_detail(device):
    """The list item plus, for a DICOM Enabler, its DICOM endpoints. A DICOM device has nothing more."""
    item = modality_list_item(device)
    if device.care_type == DICOM_ENABLER_CARE_TYPE:
        metadata = device.metadata
        item["store_scp"] = metadata.get("store_scp")
        item["modality_scp"] = metadata.get("modality_scp")
    return item
