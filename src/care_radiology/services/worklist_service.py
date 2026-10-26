import logging
from collections import defaultdict

from django.db.models import OuterRef, Q, Subquery

from care.emr.models.device import Device
from care.emr.models.location import FacilityLocation
from care.emr.models.service_request import ServiceRequest
from care.emr.resources.device.spec import DeviceAvailabilityStatusChoices, DeviceStatusChoices
from care_radiology.api.specs.external import WorklistDeviceSpec, WorklistLocationSpec
from care_radiology.models.imaging_study import ImagingStudy
from care_radiology.utils.patient import get_patient_uhid

logger = logging.getLogger(__name__)


def get_service_requests(*, facility, from_date=None, to_date=None, modality=None):
    filters = Q(facility=facility, status="active", deleted=False)

    if modality:
        location_ids = FacilityLocation.objects.filter(facility=facility, name__iexact=modality).values_list(
            "id", flat=True
        )
        filters &= Q(activity_definition__locations__overlap=location_ids)

    if from_date:
        filters &= Q(created_date__gte=from_date)

    if to_date:
        filters &= Q(created_date__lte=to_date)

    logger.info(
        "Service Request filters - modality=%s, from_date=%s, to_date=%s, facility=%s",
        modality,
        from_date,
        to_date,
        facility.external_id,
    )

    return (
        ServiceRequest.objects.filter(filters)
        .select_related("patient", "facility", "activity_definition")
        .annotate(
            accession_number=Subquery(
                ImagingStudy.objects.filter(service_request=OuterRef("pk")).values("accession_number")[:1]
            )
        )
        .order_by("-created_date")
    )


def worklist_entries(service_requests, modality=None):
    location_ids = {
        location_id
        for sr in service_requests
        for location_id in (sr.activity_definition.locations if sr.activity_definition else [])
    }

    location_objects = FacilityLocation.objects.filter(id__in=location_ids)
    if modality:
        location_objects = location_objects.filter(name__iexact=modality)
    location_objects = list(location_objects)

    devices = Device.objects.filter(
        current_location__in=location_objects,
        status=DeviceStatusChoices.active,
        availability_status=DeviceAvailabilityStatusChoices.available,
    ).order_by("registered_name", "id")
    devices_by_location = defaultdict(list)
    for device in devices:
        devices_by_location[device.current_location_id].append(WorklistDeviceSpec.serialize(device).to_json())

    locations = {
        location.id: WorklistLocationSpec.serialize(location, devices=devices_by_location[location.id]).to_json()
        for location in location_objects
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
    return {
        "service_request": {
            "id": sr.external_id,
            "name": ad.title if ad else None,
            "description": code.get("display"),
            "body_site": ad.body_site.get("display") if ad and ad.body_site else None,
            "procedure_id": code.get("code"),
            "priority": sr.priority,
            "technician_instruction": sr.note,
            "patient_instruction": sr.patient_instruction,
            "date": sr.created_date,
            "accession_number": sr.accession_number,
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
