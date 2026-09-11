import logging
import re

from care.emr.models.notes import NoteMessage, NoteThread
from care.emr.models.service_request import ServiceRequest
from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from care_radiology.models.accession_sequence import AccessionSequence

logger = logging.getLogger(__name__)


def _normalized_value(value: str, length: int = 3) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()[:length]


def _next_accession_sequence(facility, sequence_modality_key, year):
    # Atomic upsert - Postgres row lock on the ON CONFLICT branch prevents concurrent collisions.
    table = AccessionSequence._meta.db_table  # noqa: SLF001
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {table} (facility_id, modality_code, year, last_value)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (facility_id, modality_code, year)
            DO UPDATE SET last_value = {table}.last_value + 1
            RETURNING last_value
            """,  # noqa: S608
            [facility.pk, sequence_modality_key, year],
        )
        return cursor.fetchone()[0]


def generate_accession_number(service_request):
    year = timezone.now().year
    year_suffix = str(year)[-2:]

    facility = service_request.facility
    modality = service_request.code or {}

    facility_code = _normalized_value(facility.name)
    sequence_modality_key = (modality.get("code") or "")[:100]
    modality_display_code = _normalized_value(modality.get("display") or "")

    incremental_identifier = _next_accession_sequence(facility, sequence_modality_key, year)

    return f"AC{facility_code}{modality_display_code}{year_suffix}{incremental_identifier:06d}"


@shared_task
def create_radiology_note_thread(service_request_id: str):
    logger.info(
        "Creating radiology note thread for service request %s",
        service_request_id,
    )

    try:
        service_request = ServiceRequest.objects.select_related("patient", "encounter", "created_by", "facility").get(
            id=service_request_id
        )

        accession_number = service_request.meta.get("accession_number")
        if not accession_number:
            with transaction.atomic():
                locked = ServiceRequest.objects.select_for_update().only("id", "meta").get(id=service_request_id)
                accession_number = locked.meta.get("accession_number")
                if not accession_number:
                    accession_number = generate_accession_number(service_request)
                    locked.meta["accession_number"] = accession_number
                    locked.save(update_fields=["meta"])
                service_request.meta = locked.meta

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
