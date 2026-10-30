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


def _letters(index: int, length: int) -> str:
    chars = []
    for _ in range(length):
        index, remainder = divmod(index, 26)
        chars.append(chr(ord("A") + remainder))
    return "".join(reversed(chars))


def _fixed_width_code(value: int, width: int) -> str:
    """
    Encode value into exactly `width` characters.
    Digits first (e.g. width 3: 000-999), then a growing letter prefix with a
    numeric suffix starting at 1: A01..A99, B01..Z99, AA1..ZZ9, AAA..ZZZ.
    """
    if value < 10**width:
        return f"{value:0{width}d}"
    value -= 10**width
    for prefix_length in range(1, width + 1):
        suffix_width = width - prefix_length
        per_prefix = 10**suffix_width - 1 if suffix_width else 1
        block = 26**prefix_length * per_prefix
        if value < block:
            prefix_index, suffix = divmod(value, per_prefix)
            suffix_part = f"{suffix + 1:0{suffix_width}d}" if suffix_width else ""
            return _letters(prefix_index, prefix_length) + suffix_part
        value -= block
    raise ValueError(f"Value exceeds {width}-character code capacity")


def _next_accession_sequence(facility, resourcecategory_id, year):
    # Atomic upsert - Postgres row lock on the ON CONFLICT branch prevents concurrent collisions.
    table = AccessionSequence._meta.db_table  # noqa: SLF001
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {table} (facility_id, resourcecategory_id, year, last_value)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (facility_id, resourcecategory_id, year)
            DO UPDATE SET last_value = {table}.last_value + 1
            RETURNING last_value
            """,  # noqa: S608
            [facility.pk, resourcecategory_id, year],
        )
        return cursor.fetchone()[0]


def generate_accession_number(service_request):
    year = timezone.now().year
    year_suffix = str(year)[-2:]

    facility = service_request.facility
    category_id = service_request.activity_definition.category_id

    facility_code = _normalized_value(facility.name)
    category_code = _fixed_width_code(category_id, 3)

    # Sequence is keyed per category so the same category code never reuses a number.
    incremental_identifier = _next_accession_sequence(facility, category_id, year)

    return f"AC{facility_code}{category_code}{year_suffix}{_fixed_width_code(incremental_identifier, 6)}"


@shared_task
def assign_accession_number(service_request_id: str):
    try:
        with transaction.atomic():
            imaging_study = ImagingStudy.objects.select_for_update().get(service_request_id=service_request_id)
            if imaging_study.accession_number:
                return

            service_request = ServiceRequest.objects.select_related("facility", "activity_definition").get(
                id=service_request_id
            )
            imaging_study.accession_number = generate_accession_number(service_request)
            imaging_study.save(update_fields=["accession_number", "modified_date"])
    except ImagingStudy.DoesNotExist:
        logger.error("Imaging study for service request %s not found.", service_request_id)
