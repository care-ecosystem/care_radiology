import logging
from collections import defaultdict

from django.db.models import OuterRef, Q, Subquery

from care.emr.models.location import FacilityLocation
from care.emr.models.service_request import ServiceRequest
from care_radiology.api.specs.external import WorklistDeviceSpec, WorklistLocationSpec
from care_radiology.constants import DICOM_CARE_TYPE
from care_radiology.models.imaging_study import ImagingStudy
from care_radiology.services.modality_service import active_available_devices, dicom_enabler_id
from care_radiology.utils.patient import get_patient_uhid

logger = logging.getLogger(__name__)


def dicom_enabler_devices(facility, device):
    """
    The active, available DICOM devices connected to the DICOM Enabler `device` that are located in a room,
    by name, or a 400 naming the `device` filter when it is not a DICOM Enabler of the facility.
    """
    enabler_id = dicom_enabler_id(facility, device, field="device")
    return list(
        active_available_devices(facility)
        .filter(care_type=DICOM_CARE_TYPE, metadata__dicom_enabler=str(enabler_id), current_location__isnull=False)
        .order_by("registered_name", "id")
    )


def get_service_requests(*, facility, location_ids, from_date=None, to_date=None):
    """
    The facility's active service requests whose activity definition lists one of `location_ids`; none when it
    is empty.
    """
    filters = Q(
        facility=facility,
        status="active",
        deleted=False,
        activity_definition__locations__overlap=list(location_ids),
    )

    if from_date:
        filters &= Q(created_date__gte=from_date)

    if to_date:
        filters &= Q(created_date__lte=to_date)

    logger.info(
        "Service Request filters - location_ids=%s, from_date=%s, to_date=%s, facility=%s",
        location_ids,
        from_date,
        to_date,
        facility.external_id,
    )

    return (
        ServiceRequest.objects.filter(filters)
        .select_related("patient", "facility", "activity_definition", "requester")
        .annotate(
            accession_number=Subquery(
                ImagingStudy.objects.filter(service_request=OuterRef("pk")).values("accession_number")[:1]
            )
        )
        .order_by("-created_date")
    )


def worklist_entries(service_requests, enabler_devices):
    """
    Each service request with those of its activity definition's locations that `enabler_devices` (the DICOM
    devices of one DICOM Enabler) are in, each location with these devices.
    """
    location_ids = {
        location_id
        for sr in service_requests
        for location_id in (sr.activity_definition.locations if sr.activity_definition else [])
    } & {device.current_location_id for device in enabler_devices}

    devices_by_location = defaultdict(list)
    for device in enabler_devices:
        if device.current_location_id in location_ids:
            devices_by_location[device.current_location_id].append(WorklistDeviceSpec.serialize(device).to_json())

    locations = {
        location.id: WorklistLocationSpec.serialize(location, devices=devices_by_location[location.id]).to_json()
        for location in FacilityLocation.objects.filter(id__in=location_ids)
    }
    return [
        worklist_entry(
            sr,
            locations=[
                locations[i]
                for i in (sr.activity_definition.locations if sr.activity_definition else [])
                if i in locations
            ],
        )
        for sr in service_requests
    ]


def worklist_entry(sr, locations=()):
    ad = sr.activity_definition
    code = (ad.code or {}) if ad else {}
    body_site = (ad.body_site or {}) if ad else {}
    return {
        "service_request": {
            "id": sr.external_id,
            "name": ad.title if ad else None,
            "description": code.get("display"),
            "body_site": body_site.get("display"),
            "body_site_id": body_site.get("code"),
            "procedure_id": code.get("code"),
            "priority": sr.priority,
            "technician_instruction": sr.note,
            "patient_instruction": sr.patient_instruction,
            "date": sr.created_date,
            "accession_number": sr.accession_number,
            "referring_physician": sr.requester.full_name if sr.requester else None,
        },
        "locations": list(locations),
        "facility": {"id": sr.facility.external_id, "name": sr.facility.name},
        "patient": {
            "id": sr.patient.external_id,
            "name": sr.patient.name,
            "gender": sr.patient.gender,
            "age": sr.patient.age,
            "patient_uhid": get_patient_uhid(sr.patient),
        },
    }
