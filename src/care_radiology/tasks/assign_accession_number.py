import logging
import re

from care.emr.models.service_request import ServiceRequest
from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

from care_radiology.models.accession_sequence import AccessionSequence
from care_radiology.models.imaging_study import ImagingStudy

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
def assign_accession_number(service_request_id: str):
    try:
        with transaction.atomic():
            imaging_study = ImagingStudy.objects.select_for_update().get(service_request_id=service_request_id)
            if imaging_study.accession_number:
                return

            service_request = ServiceRequest.objects.select_related("facility").get(id=service_request_id)
            imaging_study.accession_number = generate_accession_number(service_request)
            imaging_study.save(update_fields=["accession_number", "modified_date"])
    except ImagingStudy.DoesNotExist:
        logger.error("Imaging study for service request %s not found.", service_request_id)
