import re

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from care.emr.models.notes import NoteMessage, NoteThread
from care.emr.models.service_request import ServiceRequest

import logging

logger = logging.getLogger(__name__)

def _normalized_value(value: str, length: int = 3) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()[:length]


def generate_accession_number(service_request):
    year = timezone.now().year
    year_suffix = str(year)[-2:]

    facility = service_request.facility
    modality = service_request.code or {}

    facility_code = _normalized_value(facility.name if facility else "")
    modality_code = _normalized_value(modality.get("display") or "")

    with transaction.atomic():
        incremental_identifier = (
            ServiceRequest.objects.filter(
                facility=facility,
                created_date__year=year,
                code__code=modality.get("code"),
            ).count()
            + 1
        )

    return (
        f"AC{facility_code}{modality_code}{year_suffix}{incremental_identifier:06d}"
    )


@shared_task
def create_radiology_note_thread(service_request_id: str):
    logger.info(
        "Creating radiology note thread for service request %s",
        service_request_id,
    )

    try:
        service_request = (
            ServiceRequest.objects
            .select_related("patient", "encounter", "created_by", "facility")
            .get(id=service_request_id)
        )

        accession_number = service_request.meta.get("accession_number")
        if not accession_number:
            accession_number = generate_accession_number(service_request)
            service_request.meta["accession_number"] = accession_number
            service_request.save(update_fields=["meta"])

        note_thread, _ = NoteThread.objects.get_or_create(
            title=f"Radiology - {accession_number}",
            patient=service_request.patient,
            encounter=service_request.encounter,
        )

        notes_msg = (
            f"Radiology Request: {accession_number}\n"
            f"Doctor's Notes: {service_request.note or '-'}\n"
            f"Patient Instructions: {service_request.patient_instruction or '-'}"
        )

        NoteMessage.objects.create(
            thread=note_thread,
            message=notes_msg,
            created_by=service_request.created_by,
        )

        logger.info(
            "Radiology note thread created for service request %s",
            service_request_id,
        )
    except ServiceRequest.DoesNotExist:
        logger.error(
            "ServiceRequest with id %s not found.",
            service_request_id,
        )
    except Exception:
        logger.exception(
            "Error creating radiology note thread for service request %s",
            service_request_id,
        )
