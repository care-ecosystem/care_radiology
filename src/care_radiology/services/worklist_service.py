import logging

from care.emr.models.device import Device
from care.emr.models.service_request import ServiceRequest
from django.db.models import Q

from care_radiology.utils.patient import get_patient_uhid

logger = logging.getLogger(__name__)


def get_service_requests(
    *,
    from_date=None,
    to_date=None,
    modality=None,
    facility=None,
    limit=1000,
):
    filters = Q(status="active", deleted=False)

    if facility:
        filters &= Q(facility=facility)

    if modality:
        device_location_ids = Device.objects.filter(registered_name__iexact=modality).values_list(
            "current_location_id", flat=True
        )
        filters &= Q(activity_definition__locations__overlap=device_location_ids)

    if from_date:
        filters &= Q(created_date__gte=from_date)

    if to_date:
        filters &= Q(created_date__lte=to_date)

    logger.info(
        "Service Request filters - modality=%s, from_date=%s, to_date=%s, facility=%s",
        modality,
        from_date,
        to_date,
        facility.external_id if facility else None,
    )

    qs = ServiceRequest.objects.filter(filters).select_related(
        "patient", "facility", "activity_definition", "created_by"
    )[:limit]

    results = []
    for sr in qs:
        name = None
        body_site = None
        description = None
        procedure_id = None
        created_by = None
        patient_uhid = None

        if sr.activity_definition is not None:
            name = sr.activity_definition.title
            if sr.activity_definition.body_site is not None:
                body_site = sr.activity_definition.body_site.get("display")
            if sr.activity_definition.code is not None:
                description = sr.activity_definition.code.get("display")
                procedure_id = sr.activity_definition.code.get("code")

        if sr.created_by is not None:
            created_by = {
                "prefix": sr.created_by.prefix,
                "first_name": sr.created_by.first_name,
                "last_name": sr.created_by.last_name,
            }

        if sr.patient is not None:
            patient_uhid = get_patient_uhid(sr.patient)

        results.append(
            {
                "service_request": {
                    "id": sr.id,
                    "external_id": sr.external_id,
                    "name": name,
                    "date": sr.created_date,
                    "meta": sr.meta,
                    "body_site": body_site,
                    "description": description,
                    "modality": modality,
                    "procedure_id": procedure_id,
                    "created_by": created_by,
                    "priority": sr.priority,
                    "technician_instruction": sr.note,
                    "patient_instruction": sr.patient_instruction,
                },
                "facility": {"id": sr.facility.external_id, "name": sr.facility.name},
                "patient": {
                    "id": sr.patient.id,
                    "external_id": sr.patient.external_id,
                    "name": sr.patient.name,
                    "address": sr.patient.address,
                    "phone_number": sr.patient.phone_number,
                    "gender": sr.patient.gender,
                    "age": sr.patient.age,
                    "patient_uhid": patient_uhid,
                },
            }
        )

    return results
