import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from care.emr.models.encounter import Encounter
from care.emr.models.service_request import ServiceRequest
from care.emr.models.tag_config import TagConfig
from care.utils.shortcuts import get_object_or_404
from care_radiology.constants import (
    ARCHIVED_STUDY_UID_FIELD,
    DCM4CHEE_ARCHIVE_BASEURL,
    DCM4CHEE_BASEURL,
    DICOM_STUDY_CACHE_KEY_TEMPLATE,
    DICOM_STUDY_LINKS_CACHE_KEY_TEMPLATE,
    DICOM_STUDY_LOCK_KEY_TEMPLATE,
    DICOM_SOP_INSTANCE_CLEANUP_MARGIN,
    DICOM_SOP_INSTANCE_CLEANUP_MARKER,
    DICOM_SOP_INSTANCE_CLEANUP_POLL_INTERVAL,
    DICOM_SOP_INSTANCE_CLEANUP_TIMEOUT,
    DICOM_SOP_INSTANCE_CLEANUP_WAIT,
    DICOM_SOP_INSTANCE_KEY_TEMPLATE,
    DICOM_SOP_INSTANCE_UPLOAD_KEY_TEMPLATE,
    DICOM_STUDY_SOP_GENERATION_KEY_TEMPLATE,
    DICOM_STUDY_UPLOAD_CACHE_TIMEOUT,
    MPPS_TAG_DISPLAY_BY_STATUS,
    PACS_DELETE_REJECTION_CODE,
)
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus
from care_radiology.settings import plugin_settings
from care_radiology.utils.patient import get_dicom_patient_id
from care_radiology.utils.dicom import (
    DICOM_TAG,
    DicomParseError,
    d_datetime_to_iso,
    d_find,
    d_query_series_for_study,
    d_query_study,
    d_query_study_sop_instance_uids,
    encode_file_multipart_related,
    read_accession_number,
    read_sop_instance_uid,
    read_study_instance_uid,
)

logger = logging.getLogger(__name__)


class DicomUploadError(Exception):
    def __init__(self, message, status_code=500, extra=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


class StudyLinkConflictError(Exception):
    def __init__(self, message, study_uid=None):
        super().__init__(message)
        self.message = message
        self.study_uid = study_uid


class PacsDeleteError(Exception):
    def __init__(self, message, status_code=502, extra=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


def _snapshot_study_details(study):
    """
    Keeps the PACS details of a study that is about to be deleted from the PACS on the record in meta
    """
    try:
        details = fetch_study(study)
    except Exception:
        logger.exception("Could not read DICOM study %s from PACS before archiving", study.dicom_study_uid)
        return
    if not details:
        return
    series = details.get("study_series") or []
    study.meta = {
        **(study.meta or {}),
        "study_date": details.get("study_date"),
        "study_description": details.get("study_description"),
        "number_of_series": len(series),
        "number_of_instances": count_study_instances(series),
    }


def _clear_study_uid(study):
    """
    Drops the Study Instance UID of a study whose files were deleted from the PACS, added reference in meta
    """
    if not study.dicom_study_uid:
        return
    study.meta = {**(study.meta or {}), ARCHIVED_STUDY_UID_FIELD: study.dicom_study_uid}
    study.dicom_study_uid = ""


def _lock_study_uid(study_uid):
    """
    Serialises the archive's PACS delete with every path that creates a DicomStudy for the
    same Study Instance UID, so the archive either sees the new record and keeps the files,
    or the new record is created only after the delete.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [DICOM_STUDY_LOCK_KEY_TEMPLATE.format(study_uid)],
        )


def _load_study_links(study_uid):
    """The imaging study, patient, encounter and service request of each active CARE record of the Study UID."""
    studies = (
        DicomStudy.objects.filter(dicom_study_uid=study_uid, is_archived=False)
        .select_related("imaging_study__encounter", "imaging_study__service_request")
        .order_by("created_date")
    )
    return [
        {
            "imaging_study_id": study.imaging_study_id,
            "patient_id": study.imaging_study.patient_id,
            "encounter_id": study.imaging_study.encounter_id,
            "encounter_external_id": str(study.imaging_study.encounter.external_id),
            "service_request_id": (
                str(study.imaging_study.service_request.external_id)
                if study.imaging_study.service_request_id is not None
                else None
            ),
        }
        for study in studies
    ]


def _cache_study_links(study_uid):
    """Caches the Study UID's links when it has active records; a new study is not cached."""
    key = DICOM_STUDY_LINKS_CACHE_KEY_TEMPLATE.format(study_uid)
    links = _load_study_links(study_uid)
    if links:
        cache.set(key, links, timeout=DICOM_STUDY_UPLOAD_CACHE_TIMEOUT)
    else:
        cache.delete(key)
    return links


def _cached_study_links(study_uid):
    key = DICOM_STUDY_LINKS_CACHE_KEY_TEMPLATE.format(study_uid)
    links = cache.get(key)
    if links is None:
        return _cache_study_links(study_uid)
    cache.touch(key, DICOM_STUDY_UPLOAD_CACHE_TIMEOUT)
    return links


def invalidate_study_upload_cache(study_uid):
    """Drops the Study UID's cached links and SOP Instance keys, after its records or its files in the PACS change."""
    cache.delete(DICOM_STUDY_LINKS_CACHE_KEY_TEMPLATE.format(study_uid))
    cache.delete(DICOM_STUDY_SOP_GENERATION_KEY_TEMPLATE.format(study_uid))


def read_file_study_uid(dcm_file):
    try:
        study_uid = read_study_instance_uid(dcm_file)
    except DicomParseError as e:
        raise _validation_error(
            "study_uid_unreadable", "Could not read the Study Instance UID from the DICOM file", details=e.message
        ) from e
    if not study_uid:
        raise _validation_error("study_uid_missing", "DICOM file does not contain a Study Instance UID")
    return study_uid


def _validate_study_links(imaging_study, study_uid):
    """
    Rejects, before the upload, a Study UID the cached links show under another patient, encounter or service
    request. The check under the Study UID lock after the upload stays the authoritative one.
    """
    try:
        _check_study_not_linked_elsewhere(imaging_study, study_uid, _cached_study_links(study_uid))
    except StudyLinkConflictError as e:
        raise _validation_error("study_link_conflict", e.message, study_uid=study_uid) from e


# SOP Instance keys outlive their generation key, which is added after them, so a generation never
# points at keys that have already expired.
_SOP_INSTANCE_KEY_TIMEOUT = DICOM_STUDY_UPLOAD_CACHE_TIMEOUT + 60


def _seed_sop_set(study_uid):
    """
    Adds a key for each instance the PACS has of the study under a new generation, and returns the generation the
    study's keys are under. Files reach the PACS only through CARE uploads, so a Study UID without a CARE record
    has nothing there and the PACS is not queried; archived records count, since an archive can leave the files
    in the PACS.
    """
    sop_instance_uids = []
    if DicomStudy.objects.filter(dicom_study_uid=study_uid).exists():
        sop_instance_uids = d_query_study_sop_instance_uids(study_uid)
        if sop_instance_uids is None:
            raise DicomUploadError(
                "Failed to query the study's instances from DCM4CHE", status_code=502, extra={"study_uid": study_uid}
            )
    generation = uuid.uuid4().hex
    cache.set_many(
        {DICOM_SOP_INSTANCE_KEY_TEMPLATE.format(study_uid, generation, uid): True for uid in sop_instance_uids},
        timeout=_SOP_INSTANCE_KEY_TIMEOUT,
    )
    generation_key = DICOM_STUDY_SOP_GENERATION_KEY_TEMPLATE.format(study_uid)
    if cache.add(generation_key, generation, timeout=DICOM_STUDY_UPLOAD_CACHE_TIMEOUT):
        return generation
    # Another upload filled the study meanwhile, adding its generation only after all of its keys.
    current = cache.get(generation_key)
    if current is None:
        # Dropped again straight away, by an archive of the study.
        raise DicomUploadError("The study changed during the upload, try again", status_code=409)
    return current


def _upload_claim_timeout():
    """Expiry of an upload claim: the upload to the PACS and the study query that follows it."""
    return (
        plugin_settings.CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT * 2
        + plugin_settings.CARE_RADIOLOGY_PACS_UPLOAD_TIMEOUT
        + plugin_settings.CARE_RADIOLOGY_PACS_QUERY_TIMEOUT
    )


def _claim_sop_instance(study_uid, sop_instance_uid):
    """
    Adds the upload claim of the SOP Instance UID and returns its key, once the study's keys, filled from the PACS
    first if needed, show the file is not stored. Returns None when another request is uploading the file or the
    PACS has it. A claim held by the cleanup of a failed upload of the file is waited for, since the cleanup
    releases it.
    """
    claim_key = DICOM_SOP_INSTANCE_UPLOAD_KEY_TEMPLATE.format(study_uid, sop_instance_uid)
    deadline = time.monotonic() + DICOM_SOP_INSTANCE_CLEANUP_WAIT
    while not cache.add(claim_key, True, timeout=_upload_claim_timeout()):
        value = cache.get(claim_key)
        if value is None:
            # Released since the add, claim it again.
            continue
        if not _is_cleanup_marker(value):
            return None
        if time.monotonic() >= deadline:
            raise DicomUploadError(
                "A failed upload of this file is still being removed from the PACS, try again shortly",
                status_code=409,
                extra={"sop_instance_uid": sop_instance_uid},
            )
        time.sleep(DICOM_SOP_INSTANCE_CLEANUP_POLL_INTERVAL)

    try:
        generation = cache.get(DICOM_STUDY_SOP_GENERATION_KEY_TEMPLATE.format(study_uid)) or _seed_sop_set(study_uid)
    except Exception:
        cache.delete(claim_key)
        raise
    if cache.get(DICOM_SOP_INSTANCE_KEY_TEMPLATE.format(study_uid, generation, sop_instance_uid)) is not None:
        cache.delete(claim_key)
        return None
    return claim_key


def _release_stored_sop_instance(study_uid, sop_instance_uid, claim_key):
    """
    Adds the key of a file the PACS stored to the study's current generation, then releases its upload claim. Run
    once the upload's record is committed, so a generation filled from the PACS after the release has the file.
    """
    try:
        generation = cache.get(DICOM_STUDY_SOP_GENERATION_KEY_TEMPLATE.format(study_uid)) or _seed_sop_set(study_uid)
        cache.set(
            DICOM_SOP_INSTANCE_KEY_TEMPLATE.format(study_uid, generation, sop_instance_uid),
            True,
            timeout=_SOP_INSTANCE_KEY_TIMEOUT,
        )
    except Exception:
        # Without a generation, the next upload of the study fills one from the PACS, which has the file.
        logger.exception("Could not add the stored file %s to the study's keys", sop_instance_uid)
    finally:
        cache.delete(claim_key)


def _is_cleanup_marker(value):
    return isinstance(value, str) and value.startswith(DICOM_SOP_INSTANCE_CLEANUP_MARKER.format(""))


def _start_failed_upload_cleanup(study_uid, sop_instance_uid, claim_key):
    """
    Hands the claim of a file whose upload to the PACS failed or timed out to a cleanup task, which removes the file
    from the PACS in case it was stored anyway and then releases the claim.
    """
    from care_radiology.tasks.cleanup_failed_upload import cleanup_failed_pacs_upload

    token = uuid.uuid4().hex
    cache.set(claim_key, DICOM_SOP_INSTANCE_CLEANUP_MARKER.format(token), timeout=DICOM_SOP_INSTANCE_CLEANUP_TIMEOUT)
    try:
        cleanup_failed_pacs_upload.delay(study_uid, sop_instance_uid, claim_key, token)
    except Exception:
        logger.exception(
            "Could not start the cleanup of the failed upload of %s, releasing its claim", sop_instance_uid
        )
        cache.delete(claim_key)


def upload_dicom_file(imaging_study, dcm_file, user=None):
    """
    Uploads a DICOM file to the PACS. Its Study UID is checked against the cached links of the study, and its
    SOP Instance UID is claimed for the upload, which rejects a file another request is uploading or that the
    study's cached SOP Instance keys show in the PACS. The claim is kept apart from those expiring keys until the
    upload's record is committed. The PACS stores the file under the CARE patient's Patient ID.
    """
    if not dcm_file:
        raise DicomUploadError("No file provided", status_code=400)

    study_uid = read_file_study_uid(dcm_file)
    _validate_study_links(imaging_study, study_uid)

    claim_key = None
    stored = False
    try:
        duplicate_check_enabled = plugin_settings.CARE_RADIOLOGY_REJECT_DUPLICATE_SOP_INSTANCE
        if not duplicate_check_enabled:
            logger.warning("DICOM duplicate check is disabled on this instance, uploading without it")

        if duplicate_check_enabled:
            sop_instance_uid = read_sop_instance_uid(dcm_file)
            if sop_instance_uid:
                claim_key = _claim_sop_instance(study_uid, sop_instance_uid)
                if claim_key is None:
                    raise DicomUploadError(
                        "Duplicate: File already uploaded.",
                        status_code=409,
                        extra={"duplicate": True, "sop_instance_uid": sop_instance_uid},
                    )

        body, content_type = encode_file_multipart_related(dcm_file)

        try:
            upload_response = requests.post(
                url=f"{DCM4CHEE_BASEURL}/rs/studies",
                # dcm4chee sets each query parameter as an attribute of the stored file, overwriting its value.
                params={"PatientID": get_dicom_patient_id(imaging_study.patient)},
                data=body,
                headers={
                    "Content-Type": content_type,
                    "Accept": "application/dicom+json",
                },
                timeout=(
                    plugin_settings.CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT,
                    plugin_settings.CARE_RADIOLOGY_PACS_UPLOAD_TIMEOUT,
                ),
            )
            if upload_response.status_code not in [200, 201]:
                raise DicomUploadError(
                    "Failed to upload to DCM4CHE",
                    status_code=502,
                    extra={"status_code": upload_response.status_code},
                )
        except (requests.RequestException, DicomUploadError) as e:
            # The PACS may have stored the file anyway, so its claim goes to the cleanup straight away.
            if claim_key:
                _start_failed_upload_cleanup(study_uid, sop_instance_uid, claim_key)
                claim_key = None
            if isinstance(e, requests.Timeout):
                raise DicomUploadError(
                    "DCM4CHE upload timeout",
                    status_code=504,
                    extra={"details": str(e)},
                ) from e
            raise
        stored = True
        if claim_key:
            transaction.on_commit(lambda: _release_stored_sop_instance(study_uid, sop_instance_uid, claim_key))

        with transaction.atomic():
            _lock_study_uid(study_uid)
            linked_elsewhere = _check_study_not_linked_elsewhere(imaging_study, study_uid, _load_study_links(study_uid))
            (dicom_study, created) = DicomStudy.objects.update_or_create(
                dicom_study_uid=study_uid,
                imaging_study=imaging_study,
                is_archived=False,
                defaults={"updated_by": user} if user else {},
                create_defaults={"created_by": user, "updated_by": user},
            )
            if created and linked_elsewhere:
                logger.warning(
                    "DICOM study validation is disabled on this instance, adding study %s to imaging study %s as well",
                    study_uid,
                    imaging_study.external_id,
                )
        if created:
            transaction.on_commit(lambda: _cache_study_links(study_uid))

        cache.delete(DICOM_STUDY_CACHE_KEY_TEMPLATE.format(study_uid))
        study_details = fetch_study(dicom_study)
        if study_details is None:
            raise DicomUploadError(
                "Upload succeeded but failed to fetch complete study details from DCM4CHE",
                status_code=500,
                extra={"study_uid": study_uid},
            )
        save_study_counts(dicom_study, study_details)

        return {
            "study_uid": study_uid,
            "study": study_details,
        }

    except (DicomUploadError, StudyLinkConflictError):
        raise
    except Exception as e:
        logger.exception("Unexpected error during DICOM upload")
        raise DicomUploadError("Exception occurred", status_code=500, extra={"details": str(e)})
    finally:
        if claim_key and not stored:
            cache.delete(claim_key)


def count_study_instances(series):
    """
    Totals the instances across a study's series, or None when a count cannot be read.
    """
    try:
        return sum(int(s["series_instance_count"][0]) for s in series if s["series_instance_count"])
    except (TypeError, ValueError):
        return None


def save_study_counts(dicom_study, study_details):
    """
    Saves the study's series and instance counts from its PACS details, only ever raising them,
    so a parallel upload that fetched the study earlier cannot lower them. An unreadable count
    is logged and skipped rather than failing the upload.
    """
    series = study_details["study_series"]
    number_of_instances = count_study_instances(series)
    if number_of_instances is None:
        logger.warning("Study %s has an unreadable series instance count, counts not updated", dicom_study.pk)
        return

    DicomStudy.objects.filter(pk=dicom_study.pk).update(
        number_of_series=Greatest("number_of_series", len(series)),
        number_of_instances=Greatest("number_of_instances", number_of_instances),
    )


def _check_study_not_linked_elsewhere(imaging_study, study_uid, links):
    """
    Rejects a Study UID that a non-archived record (one of `links`, from _load_study_links) already has under
    another imaging study. Run under the Study UID lock, concurrent uploads cannot both pass it. Returns whether
    another imaging study holds it, which is only allowed with the check disabled, and never across patients.
    """
    others = [link for link in links if link["imaging_study_id"] != imaging_study.id]
    if any(link["patient_id"] != imaging_study.patient_id for link in others):
        raise StudyLinkConflictError("Study is already linked to another patient", study_uid=study_uid)

    if not others:
        return False
    if not plugin_settings.CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR:
        return True
    other = others[0]
    other_service_request_id = other["service_request_id"]
    if other_service_request_id is None:
        if other["encounter_id"] == imaging_study.encounter_id:
            raise StudyLinkConflictError(
                "Study is already linked to this encounter without a service request", study_uid=study_uid
            )
        raise StudyLinkConflictError(
            f"Study is already linked to a different encounter: {other['encounter_external_id']}", study_uid=study_uid
        )
    raise StudyLinkConflictError(
        f"Study is already linked to a different service request: {other_service_request_id}", study_uid=study_uid
    )


def imaging_study_for_service_request(service_request):
    try:
        return service_request.imaging_study
    except ImagingStudy.DoesNotExist:
        pass
    imaging_study, _ = ImagingStudy.objects.get_or_create(
        service_request=service_request,
        defaults={"encounter_id": service_request.encounter_id, "patient_id": service_request.patient_id},
    )
    return imaging_study


def _validation_error(error_type, msg, **extra):
    # emr_exception_handler returns an {"errors": [...]} detail as is, with status 400.
    return ValidationError({"errors": [{"type": error_type, "msg": msg, **extra}]})


def read_file_accession_number(dcm_file):
    try:
        accession_number = read_accession_number(dcm_file)
    except DicomParseError as e:
        raise _validation_error(
            "accession_number_unreadable",
            "Could not read the accession number from the DICOM file",
            details=e.message,
        ) from e
    if not accession_number:
        raise _validation_error("accession_number_missing", "DICOM file does not contain an accession number")
    return accession_number


def validate_accession_number(dcm_file, service_request):
    file_accession_number = read_file_accession_number(dcm_file)
    try:
        imaging_study = service_request.imaging_study
    except ImagingStudy.DoesNotExist:
        raise _validation_error(
            "imaging_study_missing", "Service request has no imaging study to match the accession number against"
        ) from None
    if file_accession_number != imaging_study.accession_number:
        raise _validation_error(
            "accession_number_mismatch", "Accession number in the DICOM file does not match the service request"
        )


def imaging_study_for_accession_number(accession_number, facility):
    """Returns the newest non-cancelled imaging study in the facility with this accession number."""
    imaging_study = (
        ImagingStudy.objects.filter(
            accession_number=accession_number,
            service_request__facility=facility,
            service_request__deleted=False,
        )
        .exclude(status=ImagingStudyStatus.CANCELLED)
        .select_related("service_request")
        .order_by("-created_date")
        .first()
    )
    if imaging_study is None:
        raise _validation_error(
            "accession_number_unmatched",
            "No imaging study in the facility has the file's accession number",
        )
    return imaging_study


def imaging_study_for_encounter(encounter):
    """Returns the encounter's one imaging study without a service request, creating it on first use."""
    imaging_studies = ImagingStudy.objects.filter(encounter=encounter, service_request__isnull=True)
    imaging_study = imaging_studies.first()
    if imaging_study is None:
        with transaction.atomic():
            # Serialises the creation of that imaging study per encounter.
            Encounter.objects.select_for_update().filter(pk=encounter.pk).first()
            imaging_study = imaging_studies.first() or ImagingStudy.objects.create(
                encounter=encounter, patient_id=encounter.patient_id
            )
    return imaging_study


def process_mpps_webhook(facility, service_request_id, study_status, user):
    """
    Sets the service request's imaging study to `study_status`, then adds the facility tag whose
    display is the status's MPPS status (Scan Started, Scan Completed or Scan Cancelled) to the
    service request, when the facility has one. An imaging study already COMPLETED or CANCELLED
    keeps its status.
    """
    tag_display = MPPS_TAG_DISPLAY_BY_STATUS[study_status]
    with transaction.atomic():
        service_request = get_object_or_404(
            ServiceRequest.objects.select_for_update(), external_id=service_request_id, facility=facility
        )
        imaging_study = get_object_or_404(ImagingStudy.objects.select_for_update(), service_request=service_request)

        if imaging_study.status not in [ImagingStudyStatus.COMPLETED, ImagingStudyStatus.CANCELLED]:
            imaging_study.status = study_status
            imaging_study.save(update_fields=["status", "modified_date"])

        try:
            tag_config = TagConfig.objects.filter(facility=facility, display=tag_display).first()
        except Exception as e:
            logger.exception("[MPPS] Error fetching tag")
            raise APIException("Error fetching tag configuration") from e

        tags = service_request.tags or []
        if not tag_config:
            logger.info("[MPPS] No tag configured for %s, skipping tag update", tag_display)
        elif tag_config.id in tags:
            logger.warning(
                "[MPPS] Tag %s already exists in SR %s, skipping duplicate",
                tag_config.id,
                service_request.external_id,
            )
            return {
                "detail": "Tag already set for this service request",
                "service_request_id": str(service_request.external_id),
                "study_status": study_status,
                "tag_id": tag_config.id,
            }
        else:
            try:
                tags.append(tag_config.id)
                service_request.tags = tags
                service_request.updated_by = user
                service_request.save(update_fields=["tags", "updated_by", "modified_date"])
            except Exception as e:
                logger.exception("[MPPS] Error updating tags")
                raise APIException("Error updating tags") from e
            logger.info("[MPPS] Tag %s appended to ServiceRequest tags", tag_config.id)

    return {
        "detail": "MPPS status processed successfully",
        "service_request_id": str(service_request.external_id),
        "study_status": study_status,
        "tag_id": tag_config.id if tag_config else None,
        "tag_uuid": str(tag_config.external_id) if tag_config else None,
        "current_tags": tags,
    }


def fetch_study(dicom_study):
    def first(dcm, tag):
        values = d_find(dcm, tag)
        return values[0] if values else None

    study_uid = dicom_study.dicom_study_uid
    if not study_uid:
        return None
    key = DICOM_STUDY_CACHE_KEY_TEMPLATE.format(study_uid)
    # The cache is per Study UID, which an archived record and its re-upload share, so the
    # record's own external_id is added on every return rather than cached.
    cached = cache.get(key)
    if cached:
        return {**cached, "id": dicom_study.external_id}

    study = d_query_study(study_uid)

    if study is None:
        return None

    series_data = d_query_series_for_study(study_uid)
    if series_data is None:
        return None

    series = [
        {
            "series_uid": d_find(s, DICOM_TAG.SeriesInstanceUID.value)[0],
            "series_number": d_find(s, DICOM_TAG.SeriesNumber.value),
            "series_instance_count": d_find(s, DICOM_TAG.NumberOfSeriesRelatedInstances.value),
            "series_description": d_find(s, DICOM_TAG.SeriesDescription.value),
            "series_modality": d_find(s, DICOM_TAG.SeriesModality.value),
        }
        for s in series_data
    ]

    study_description = (
        d_find(study, DICOM_TAG.StudyDescription.value)[0]
        if len(d_find(study, DICOM_TAG.StudyDescription.value)) > 0
        else None
    )

    study_date_raw = first(study, DICOM_TAG.StudyDate.value)
    study_time_raw = first(study, DICOM_TAG.StudyTime.value)
    study_tz_offset_raw = first(study, DICOM_TAG.TimezoneOffsetFromUTC.value)
    study_date = d_datetime_to_iso(study_date_raw, study_time_raw, study_tz_offset_raw)

    cachable = {
        "study_uid": study_uid,
        "study_date": study_date,
        "study_description": study_description,
        "study_modalities": d_find(study, DICOM_TAG.StudyModalities.value),
        "study_series": series,
    }

    cache.set(key, cachable, timeout=60 * 60)
    return {**cachable, "id": dicom_study.external_id}


def fetch_studies(dicom_studies):
    """
    Fetches the PACS details of each study in parallel and returns them keyed by study id. A study
    whose details cannot be fetched is logged and left out, as is one that has no Study UID left,
    whose files were deleted from the PACS when it was archived.
    """

    def fetch_or_none(dicom_study):
        try:
            return fetch_study(dicom_study)
        except Exception:
            logger.exception("Could not fetch study %s from PACS", dicom_study.dicom_study_uid)
            return None

    dicom_studies = [study for study in dicom_studies if study.dicom_study_uid]
    if not dicom_studies:
        return {}
    with ThreadPoolExecutor(max_workers=min(10, len(dicom_studies))) as executor:
        results = executor.map(fetch_or_none, dicom_studies)
    return {study.id: details for study, details in zip(dicom_studies, results, strict=True) if details}


def _pacs_delete_timeout():
    return (
        plugin_settings.CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT,
        plugin_settings.CARE_RADIOLOGY_PACS_QUERY_TIMEOUT,
    )


def _pacs_request(method, url, study_uid, step):
    """
    Sends one step of the delete. Returns True when the PACS acted on the study and
    False when it has no such study (404), so a repeated delete is a no-op.
    """
    try:
        response = requests.request(method, url, timeout=_pacs_delete_timeout())
    except requests.RequestException as e:
        raise PacsDeleteError(
            f"Failed to {step} study in PACS",
            status_code=504 if isinstance(e, requests.Timeout) else 502,
            extra={"study_uid": study_uid, "details": str(e)},
        ) from e

    if response.status_code == 404:
        return False
    if not response.ok:
        raise PacsDeleteError(
            f"Failed to {step} study in PACS",
            extra={"study_uid": study_uid, "status_code": response.status_code},
        )
    return True


def delete_study_from_pacs(study_uid):
    """
    Permanently removes every file of a study from dcm4chee, and with it the study's
    records in the PACS database.

    dcm4chee only deletes a study permanently once it is rejected, so the study is first
    rejected with PACS_DELETE_REJECTION_CODE and then deleted.
    """
    base_url = f"{DCM4CHEE_BASEURL}/rs/studies/{quote(study_uid, safe='')}"
    rejection_code = quote(PACS_DELETE_REJECTION_CODE, safe="")

    rejected = _pacs_request("POST", f"{base_url}/reject/{rejection_code}", study_uid, "reject")
    deleted = _pacs_request("DELETE", base_url, study_uid, "delete")

    cache.delete(DICOM_STUDY_CACHE_KEY_TEMPLATE.format(study_uid))

    if rejected or deleted:
        logger.info("Deleted DICOM study %s from PACS", study_uid)
    else:
        logger.info("DICOM study %s was not found in PACS, nothing to delete", study_uid)
    return deleted


def _find_instance_series_uid(study_uid, sop_instance_uid):
    """The Series UID of the instance in the PACS, or None when the PACS does not have it."""
    try:
        response = requests.get(
            f"{DCM4CHEE_BASEURL}/rs/studies/{quote(study_uid, safe='')}/instances",
            params={"SOPInstanceUID": sop_instance_uid, "includefield": DICOM_TAG.SeriesInstanceUID.value},
            headers={"Accept": "application/dicom+json"},
            timeout=_pacs_delete_timeout(),
        )
    except requests.RequestException as e:
        raise PacsDeleteError(
            "Failed to find instance in PACS",
            status_code=504 if isinstance(e, requests.Timeout) else 502,
            extra={"study_uid": study_uid, "details": str(e)},
        ) from e
    # QIDO-RS answers a query with no matches with 204 and no body.
    if response.status_code in (204, 404):
        return None
    if not response.ok:
        raise PacsDeleteError(
            "Failed to find instance in PACS", extra={"study_uid": study_uid, "status_code": response.status_code}
        )
    instances = response.json()
    return d_find(instances[0], DICOM_TAG.SeriesInstanceUID.value)[0] if instances else None


def delete_instance_from_pacs(study_uid, sop_instance_uid, before_request=None):
    """
    Permanently removes one instance from dcm4chee, returning whether the PACS had it.

    dcm4chee keeps a rejected instance and silently discards a later store of it, so the instance is rejected with
    PACS_DELETE_REJECTION_CODE and then the instances rejected with that code are deleted, which lets the file be
    stored again. `before_request`, when given, is called before each PACS request and may raise to stop the delete.
    """
    before_request = before_request or (lambda: None)
    before_request()
    series_uid = _find_instance_series_uid(study_uid, sop_instance_uid)
    if series_uid is None:
        return False
    rejection_code = quote(PACS_DELETE_REJECTION_CODE, safe="")
    instance_url = (
        f"{DCM4CHEE_BASEURL}/rs/studies/{quote(study_uid, safe='')}/series/{quote(series_uid, safe='')}"
        f"/instances/{quote(sop_instance_uid, safe='')}"
    )
    before_request()
    _pacs_request("POST", f"{instance_url}/reject/{rejection_code}", study_uid, "reject")
    before_request()
    _pacs_request("DELETE", f"{DCM4CHEE_ARCHIVE_BASEURL}/reject/{rejection_code}", study_uid, "delete")
    cache.delete(DICOM_STUDY_CACHE_KEY_TEMPLATE.format(study_uid))
    logger.info("Deleted instance %s of DICOM study %s from PACS", sop_instance_uid, study_uid)
    return True


class CleanupClaimLost(Exception):
    """The claim no longer holds the cleanup's marker, or cannot be kept long enough for its next PACS request."""


def _cleanup_request_timeout():
    """Longest one PACS request of a cleanup can take: connecting, then reading the response."""
    return plugin_settings.CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT + plugin_settings.CARE_RADIOLOGY_PACS_QUERY_TIMEOUT


def _claim_ttl(claim_key):
    """Seconds left before the claim expires, None when the cache cannot tell (only django-redis can)."""
    ttl = getattr(cache, "ttl", None)
    return ttl(claim_key) if ttl else None


def _hold_cleanup_claim(claim_key, token, seconds):
    """
    Makes sure the claim holds this cleanup's marker for at least `seconds` more, extending it when needed, so no
    upload can claim the file before a request sent now finishes. Raises CleanupClaimLost otherwise.

    The TTL is read before the marker: a marker read right after a TTL above the margin is the same key, and it
    cannot expire before the extension that follows. A marker nearer to expiry is not extended, since an upload
    could claim the file between the read and the extension.
    """
    remaining = _claim_ttl(claim_key)
    if cache.get(claim_key) != DICOM_SOP_INSTANCE_CLEANUP_MARKER.format(token):
        raise CleanupClaimLost
    if remaining is not None:
        if remaining >= seconds + DICOM_SOP_INSTANCE_CLEANUP_MARGIN:
            return
        if remaining <= DICOM_SOP_INSTANCE_CLEANUP_MARGIN:
            raise CleanupClaimLost
    if not cache.touch(claim_key, seconds + DICOM_SOP_INSTANCE_CLEANUP_MARGIN):
        raise CleanupClaimLost


def cleanup_failed_upload(study_uid, sop_instance_uid, claim_key, token):
    """
    Removes the file of a failed upload from the PACS, in case the PACS stored it anyway, then drops the study's
    upload cache when the PACS has nothing else of the study, and releases the file's claim, which is released
    as well when the PACS does not have the file.

    The claim keeps this cleanup's marker until every PACS request and the cache drop are done: before each one the
    marker is checked and extended to outlast it, so a new upload of the file cannot start while the cleanup may
    still delete it. Stopped, leaving the claim to expire, when the marker expired or is too close to expiry: a
    later upload of the file may hold the claim by then.
    Raises PacsDeleteError, keeping the claim, when the PACS cannot be reached.
    """

    def hold():
        _hold_cleanup_claim(claim_key, token, _cleanup_request_timeout())

    try:
        delete_instance_from_pacs(study_uid, sop_instance_uid, before_request=hold)
        hold()
        if d_query_study_sop_instance_uids(study_uid) == []:
            hold()
            invalidate_study_upload_cache(study_uid)
    except CleanupClaimLost:
        logger.warning("Claim of the failed upload of %s expired during its cleanup, stopped", sop_instance_uid)
        return
    release_failed_upload_claim(claim_key, token)


def release_failed_upload_claim(claim_key, token):
    """
    Releases the claim when it holds this cleanup's marker. A marker too close to expiry is left to expire, as an
    upload could claim the file between the read and the delete, which would then drop that upload's claim.
    """
    remaining = _claim_ttl(claim_key)
    if remaining is not None and remaining <= DICOM_SOP_INSTANCE_CLEANUP_MARGIN:
        return
    if cache.get(claim_key) == DICOM_SOP_INSTANCE_CLEANUP_MARKER.format(token):
        cache.delete(claim_key)


def archive_study(study, archive_reason, archived_by=None):
    """
    Shared by the manual archive action and the auto-archive celery task.
    `archived_by` is None for system-initiated (auto) archiving.

    With CARE_RADIOLOGY_DELETE_STUDY_FROM_PACS_ON_ARCHIVE enabled, the study's files are
    deleted from the PACS first; if that fails, PacsDeleteError is raised and the study
    is left unarchived so the archive can be retried. A study deleted from the PACS keeps its
    PACS details in `meta` and has its Study Instance UID cleared, as does any earlier archived
    record of the same UID, since their files are gone too. The CARE records are kept and stay
    listed as archived, with their archive reason and the details kept on the record itself.
    """
    # Taken before the archive clears it from a study deleted from the PACS.
    study_uid = study.dicom_study_uid
    with transaction.atomic():
        deleted_from_pacs = False
        if plugin_settings.CARE_RADIOLOGY_DELETE_STUDY_FROM_PACS_ON_ARCHIVE:
            _lock_study_uid(study.dicom_study_uid)

            # The same Study Instance UID can be recorded against more than one patient; its
            # files stay in the PACS while any other record still shows them.
            still_in_use = (
                DicomStudy.objects.filter(dicom_study_uid=study.dicom_study_uid, is_archived=False, deleted=False)
                .exclude(pk=study.pk)
                .exists()
            )
            if still_in_use:
                logger.warning(
                    "DICOM study %s is still referenced by another unarchived study, keeping it in PACS",
                    study.dicom_study_uid,
                )
            else:
                siblings = list(
                    DicomStudy.objects.filter(
                        dicom_study_uid=study.dicom_study_uid, is_archived=True
                    ).exclude(pk=study.pk)
                )
                for record in (study, *siblings):
                    _snapshot_study_details(record)

                delete_study_from_pacs(study.dicom_study_uid)
                deleted_from_pacs = True

                for sibling in siblings:
                    _clear_study_uid(sibling)
                    sibling.save(update_fields=["dicom_study_uid", "meta", "modified_date"])

        study.is_archived = True
        study.archive_reason = archive_reason
        study.archived_datetime = timezone.now()
        study.archived_by = archived_by
        if deleted_from_pacs:
            _clear_study_uid(study)
        update_fields = [
            "is_archived",
            "archive_reason",
            "archived_datetime",
            "archived_by",
            "dicom_study_uid",
            "meta",
            "modified_date",
        ]
        if archived_by:
            study.updated_by = archived_by
            update_fields.append("updated_by")
        study.save(update_fields=update_fields)
        transaction.on_commit(lambda: invalidate_study_upload_cache(study_uid))

    return study

