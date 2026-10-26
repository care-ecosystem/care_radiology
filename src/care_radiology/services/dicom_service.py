import logging
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
    DCM4CHEE_BASEURL,
    DICOM_STUDY_CACHE_KEY_TEMPLATE,
    DICOM_STUDY_LOCK_KEY_TEMPLATE,
    DICOM_UPLOAD_LOCK_KEY_TEMPLATE,
    MPPS_TAG_DISPLAY_BY_STATUS,
    PACS_DELETE_REJECTION_CODE,
)
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus
from care_radiology.settings import plugin_settings
from care_radiology.utils.dicom import (
    DICOM_TAG,
    DicomParseError,
    d_datetime_to_iso,
    d_find,
    d_query_instance,
    d_query_series_for_study,
    d_query_study,
    encode_file_multipart_related,
    read_accession_number,
    read_sop_instance_uid,
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


def _upload_lock_timeout():
    """
    Upper bound on how long the locked section can take, so a worker killed mid-upload
    cannot strand the lock: the PACS calls it covers are the duplicate query, the STOW-RS
    upload and the metadata queries that follow, each bounded by its own request timeout.
    """
    return (
        plugin_settings.CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT
        + plugin_settings.CARE_RADIOLOGY_PACS_UPLOAD_TIMEOUT
        + plugin_settings.CARE_RADIOLOGY_PACS_QUERY_TIMEOUT
    )


def upload_dicom_file(imaging_study, dcm_file, user=None):
    """Upload a DICOM file after rejecting an existing SOP Instance UID."""
    if not dcm_file:
        raise DicomUploadError("No file provided", status_code=400)

    lock_key = None
    try:
        duplicate_check_enabled = plugin_settings.CARE_RADIOLOGY_REJECT_DUPLICATE_SOP_INSTANCE
        if not duplicate_check_enabled:
            logger.warning("DICOM duplicate check is disabled on this instance, uploading without it")

        sop_instance_uid = read_sop_instance_uid(dcm_file) if duplicate_check_enabled else None

        if sop_instance_uid:
            candidate_key = DICOM_UPLOAD_LOCK_KEY_TEMPLATE.format(sop_instance_uid)

            if cache.add(candidate_key, True, timeout=_upload_lock_timeout()) is False:
                raise DicomUploadError(
                    "Duplicate: File already uploaded.",
                    status_code=409,
                    extra={
                        "duplicate": True,
                        "sop_instance_uid": sop_instance_uid,
                        "concurrent": True,
                    },
                )

            lock_key = candidate_key

            if d_query_instance(sop_instance_uid) is not None:
                raise DicomUploadError(
                    "Duplicate: File already uploaded.",
                    status_code=409,
                    extra={"duplicate": True, "sop_instance_uid": sop_instance_uid},
                )

        body, content_type = encode_file_multipart_related(dcm_file)

        try:
            upload_response = requests.post(
                url=f"{DCM4CHEE_BASEURL}/rs/studies",
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
        except requests.Timeout as e:
            raise DicomUploadError(
                "DCM4CHE upload timeout",
                status_code=504,
                extra={"details": str(e)},
            )

        if upload_response.status_code not in [200, 201]:
            raise DicomUploadError(
                "Failed to upload to DCM4CHE",
                status_code=502,
                extra={"status_code": upload_response.status_code},
            )

        referenced_sop = d_find(upload_response.json(), DICOM_TAG.ReferencedSOPSQ.value)[0]

        instance_uid = d_find(referenced_sop, DICOM_TAG.ReferencedInstanceUID.value)[0]

        instance_data = d_query_instance(instance_uid)
        if instance_data is None:
            raise DicomUploadError(
                "Upload succeeded but failed to query study metadata from DCM4CHE",
                status_code=500,
                extra={"instance_uid": instance_uid},
            )

        study_uid = d_find(instance_data, DICOM_TAG.StudyInstanceUID.value)[0]
        with transaction.atomic():
            _lock_study_uid(study_uid)
            linked_elsewhere = _check_study_not_linked_elsewhere(imaging_study, study_uid)
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
        # Released on failure too, so a retry is not blocked until the lock expires.
        if lock_key:
            cache.delete(lock_key)


def save_study_counts(dicom_study, study_details):
    """
    Saves the study's series and instance counts from its PACS details, only ever raising them,
    so a parallel upload that fetched the study earlier cannot lower them. An unreadable count
    is logged and skipped rather than failing the upload.
    """
    series = study_details["study_series"]
    try:
        number_of_instances = sum(int(s["series_instance_count"][0]) for s in series if s["series_instance_count"])
    except (TypeError, ValueError):
        logger.warning("Study %s has an unreadable series instance count, counts not updated", dicom_study.pk)
        return

    DicomStudy.objects.filter(pk=dicom_study.pk).update(
        number_of_series=Greatest("number_of_series", len(series)),
        number_of_instances=Greatest("number_of_instances", number_of_instances),
    )


def _check_study_not_linked_elsewhere(imaging_study, study_uid):
    """
    Rejects a Study UID that a non-archived record already has under another imaging study. Runs
    under the Study UID lock, so concurrent uploads cannot both pass it. Returns whether another
    imaging study holds it, which is only allowed with the check disabled, and never across patients.
    """
    others = DicomStudy.objects.filter(dicom_study_uid=study_uid, is_archived=False).exclude(
        imaging_study=imaging_study
    )
    # Checked over every record rather than one, since with the check disabled the UID can
    # already sit under several imaging studies.
    if others.exclude(imaging_study__patient_id=imaging_study.patient_id).exists():
        raise StudyLinkConflictError("Study is already linked to another patient", study_uid=study_uid)

    linked_elsewhere = others.select_related("imaging_study__service_request").first()
    if linked_elsewhere is None:
        return False
    if not plugin_settings.CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR:
        return True
    other = linked_elsewhere.imaging_study.service_request
    if other is None:
        raise StudyLinkConflictError("Study is already linked to a different imaging study", study_uid=study_uid)
    raise StudyLinkConflictError(
        f"Study is already linked to a different service request: {other.external_id}", study_uid=study_uid
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


def _accession_error(error_type, msg, **extra):
    # emr_exception_handler returns an {"errors": [...]} detail as is, with status 400.
    return ValidationError({"errors": [{"type": error_type, "msg": msg, **extra}]})


def read_file_accession_number(dcm_file):
    try:
        accession_number = read_accession_number(dcm_file)
    except DicomParseError as e:
        raise _accession_error(
            "accession_number_unreadable",
            "Could not read the accession number from the DICOM file",
            details=e.message,
        ) from e
    if not accession_number:
        raise _accession_error("accession_number_missing", "DICOM file does not contain an accession number")
    return accession_number


def validate_accession_number(dcm_file, service_request):
    file_accession_number = read_file_accession_number(dcm_file)
    try:
        imaging_study = service_request.imaging_study
    except ImagingStudy.DoesNotExist:
        raise _accession_error(
            "imaging_study_missing", "Service request has no imaging study to match the accession number against"
        ) from None
    if file_accession_number != imaging_study.accession_number:
        raise _accession_error(
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
        raise _accession_error(
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


def process_mpps_webhook(facility, service_request_id, study_status):
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
                service_request.save(update_fields=["tags"])
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
    whose details cannot be fetched is logged and left out.
    """

    def fetch_or_none(dicom_study):
        try:
            return fetch_study(dicom_study)
        except Exception:
            logger.exception("Could not fetch study %s from PACS", dicom_study.dicom_study_uid)
            return None

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


def archive_study(study, archive_reason, archived_by=None):
    """
    Shared by the manual archive action and the auto-archive celery task.
    `archived_by` is None for system-initiated (auto) archiving.

    With CARE_RADIOLOGY_DELETE_STUDY_FROM_PACS_ON_ARCHIVE enabled, the study's files are
    deleted from the PACS first; if that fails, PacsDeleteError is raised and the study
    is left unarchived so the archive can be retried. A study deleted from the PACS is
    also soft-deleted in CARE, along with any earlier archived records of the same Study
    Instance UID.
    """
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
                delete_study_from_pacs(study.dicom_study_uid)
                deleted_from_pacs = True

                DicomStudy.objects.filter(
                    dicom_study_uid=study.dicom_study_uid, is_archived=True, deleted=False
                ).exclude(pk=study.pk).update(deleted=True, modified_date=timezone.now())

        study.is_archived = True
        study.archive_reason = archive_reason
        study.archived_datetime = timezone.now()
        study.archived_by = archived_by
        study.deleted = study.deleted or deleted_from_pacs
        update_fields = [
            "is_archived",
            "archive_reason",
            "archived_datetime",
            "archived_by",
            "deleted",
            "modified_date",
        ]
        if archived_by:
            study.updated_by = archived_by
            update_fields.append("updated_by")
        study.save(update_fields=update_fields)

    return study
