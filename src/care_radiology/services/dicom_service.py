import logging
from urllib.parse import quote

import requests
from care.emr.models.service_request import ServiceRequest
from care.emr.models.tag_config import TagConfig
from care.utils.shortcuts import get_object_or_404
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from care_radiology.constants import (
    DCM4CHEE_BASEURL,
    DICOM_STUDY_CACHE_KEY_TEMPLATE,
    DICOM_STUDY_LINK_CACHE_KEY_TEMPLATE,
    DICOM_STUDY_LINK_CACHE_TIMEOUT_SECONDS,
    DICOM_STUDY_LOCK_KEY_TEMPLATE,
    DICOM_UPLOAD_LOCK_KEY_TEMPLATE,
    MPPS_STATUS_DISCONTINUED,
    MPPS_STATUS_SCAN_STARTED,
    PACS_DELETE_REJECTION_CODE,
    VALID_MPPS_STATUSES,
)
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.radiology_service_request import RadiologyServiceRequest, RadiologyServiceRequestStatus
from care_radiology.settings import plugin_settings
from care_radiology.utils.dicom import (
    DICOM_TAG,
    d_datetime_to_iso,
    d_find,
    d_query_instance,
    d_query_series_for_study,
    d_query_study,
    encode_file_multipart_related,
    read_sop_instance_uid,
)

logger = logging.getLogger(__name__)


class DicomUploadError(Exception):
    def __init__(self, message, status_code=500, extra=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


class WebhookConflictError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


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


def upload_dicom_file(patient, dcm_file):
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
            (dicom_study, _) = DicomStudy.objects.update_or_create(
                dicom_study_uid=study_uid,
                patient=patient,
                is_archived=False,
                defaults={},
            )

            key = DICOM_STUDY_CACHE_KEY_TEMPLATE.format(study_uid)
            cache.delete(key)

            study_details = fetch_study(dicom_study)
            if study_details is None:
                raise DicomUploadError(
                    "Upload succeeded but failed to fetch complete study details from DCM4CHE",
                    status_code=500,
                    extra={"study_uid": study_uid},
                )

        return {
            "study_uid": study_uid,
            "study": study_details,
        }

    except DicomUploadError:
        raise
    except Exception as e:
        logger.exception("Unexpected error during DICOM upload")
        raise DicomUploadError("Exception occurred", status_code=500, extra={"details": str(e)})
    finally:
        # Released on failure too, so a retry is not blocked until the lock expires.
        if lock_key:
            cache.delete(lock_key)


def link_service_request_to_study(service_request, study_uid, raw_data=None):
    with transaction.atomic():
        (rsr, created) = RadiologyServiceRequest.objects.get_or_create(
            service_request=service_request, defaults={"raw_data": raw_data} if raw_data is not None else {}
        )
        if not created and raw_data is not None:
            rsr.raw_data = raw_data
            rsr.save(update_fields=["raw_data"])

        # select_for_update() makes a concurrent get_or_create() for the same
        # (patient, study_uid) block on this row (or on the insert) rather than
        # racing past the check below with stale data.
        _lock_study_uid(study_uid)
        study, _ = DicomStudy.objects.select_for_update().get_or_create(
            dicom_study_uid=study_uid, patient=service_request.patient, is_archived=False
        )
        if study.radiology_service_request_id is not None and study.radiology_service_request_id != rsr.id:
            if plugin_settings.CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR:
                raise WebhookConflictError("Study is already linked to a different service request")
            logger.warning(
                "DICOM study validation is disabled on this instance, relinking study %s to service request %s",
                study_uid,
                service_request.external_id,
            )

        if study.radiology_service_request_id != rsr.id:
            study.radiology_service_request = rsr
            study.save(update_fields=["radiology_service_request"])

        if rsr.status != RadiologyServiceRequestStatus.CANCELLED:
            rsr.status = RadiologyServiceRequestStatus.COMPLETED
            rsr.save(update_fields=["status"])

    return {
        "external_id": rsr.external_id,
        "data": rsr.raw_data,
        "status": rsr.status,
    }


def ensure_study_linked_to_service_request(service_request, study_uid):
    """
    Links a newly uploaded study to its service request if not already linked, returning True 
    if linked and False if no action was needed. Raises WebhookConflictError for conflicts 
    (unless validation is disabled), with results cached per study/request pair.
    """
    cache_key = DICOM_STUDY_LINK_CACHE_KEY_TEMPLATE.format(study_uid, service_request.external_id)
    if cache.get(cache_key):
        return False

    linked_service_requests = set(
        DicomStudy.objects.filter(
            dicom_study_uid=study_uid,
            radiology_service_request__isnull=False,
            is_archived=False,
            deleted=False,
        ).values_list("radiology_service_request__service_request__external_id", flat=True)
    )

    if service_request.external_id in linked_service_requests:
        newly_linked = False
    elif linked_service_requests and plugin_settings.CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR:
        # Left uncached: an operator undoing the other link has to take effect at once.
        other = sorted(str(sr_id) for sr_id in linked_service_requests)[0]
        raise WebhookConflictError(f"Study is already linked to a different service request: {other}")
    else:
        link_service_request_to_study(service_request, study_uid)
        newly_linked = True

    cache.set(cache_key, True, timeout=DICOM_STUDY_LINK_CACHE_TIMEOUT_SECONDS)
    return newly_linked


def process_study_webhook(data):
    # Support lookup by either service_request_id or accession_number
    if (data.get("service_request_id") or data.get("accession_number")) and data.get("study_id"):
        try:
            if data.get("service_request_id"):
                # Priority 1: Lookup by service_request_id (external_id)
                sr = ServiceRequest.objects.get(external_id=data["service_request_id"])
            elif data.get("accession_number"):
                # Priority 2: Lookup by accession_number on RadiologyServiceRequest

                # If accession_number is duplicated across ServiceRequests, ignore older
                # ones and use the most recently created match instead of failing:
                rsr = (
                    RadiologyServiceRequest.objects.filter(accession_number=data["accession_number"])
                    .order_by("-created_date")
                    .select_related("service_request")
                    .first()
                )
                sr = rsr.service_request if rsr else None
                if sr is None:
                    raise ServiceRequest.DoesNotExist
            else:
                raise WebhookConflictError("No service_request_id or accession_number provided")
        except ServiceRequest.DoesNotExist:
            raise WebhookConflictError("No matching service request")

        return link_service_request_to_study(sr, data["study_id"], raw_data=data)

    elif data.get("patient_id") and data.get("study_id"):
        from care.emr.models.patient import Patient

        patient = Patient.objects.filter(instance_identifiers__contains=[{"value": data.get("patient_id")}]).first()
        if not patient:
            raise WebhookConflictError("No matching patient")

        with transaction.atomic():
            _lock_study_uid(data.get("study_id"))
            (study, _) = DicomStudy.objects.get_or_create(
                dicom_study_uid=data.get("study_id"), patient=patient, is_archived=False, defaults={}
            )

        return {
            "external_id": study.external_id,
            "data": data,
        }

    return None


def process_mpps_webhook(service_request_id, study_status):
    if study_status not in VALID_MPPS_STATUSES:
        logger.warning("[MPPS] Unexpected status: %s", study_status)

    with transaction.atomic():
        service_request = get_object_or_404(ServiceRequest.objects.select_for_update(), external_id=service_request_id)

        facility = service_request.facility
        if not facility:
            logger.error("[MPPS] Facility not found for SR")
            raise ValidationError({"service_request_id": "Facility not found for service request"})
        logger.info("[MPPS] Facility found: %s", facility.external_id)

        try:
            tag_config = TagConfig.objects.filter(facility=facility, display=study_status).first()
        except Exception as e:
            logger.exception("[MPPS] Error fetching tag")
            raise APIException("Error fetching tag configuration") from e

        if not tag_config:
            logger.error("[MPPS] Tag not found for status: %s", study_status)
            raise ValidationError({"study_status": f"Tag configuration not found for status: {study_status}"})
        logger.info("[MPPS] Tag found: %s", tag_config.external_id)

        tags = service_request.tags or []
        if tag_config.id in tags:
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

        try:
            tags.append(tag_config.id)
            service_request.tags = tags
            service_request.save(update_fields=["tags"])
        except Exception as e:
            logger.exception("[MPPS] Error updating tags")
            raise APIException("Error updating tags") from e

        if study_status == MPPS_STATUS_SCAN_STARTED:
            rsr_status = RadiologyServiceRequestStatus.IN_PROGRESS
        elif study_status == MPPS_STATUS_DISCONTINUED:
            rsr_status = RadiologyServiceRequestStatus.CANCELLED
        else:
            rsr_status = None

        if rsr_status:
            RadiologyServiceRequest.objects.filter(service_request=service_request).exclude(
                status__in=[RadiologyServiceRequestStatus.COMPLETED, RadiologyServiceRequestStatus.CANCELLED]
            ).update(status=rsr_status)

    logger.info("[MPPS] Tag %s appended to ServiceRequest tags", tag_config.id)
    logger.info("[MPPS] Success! MPPS status tag updated via direct database write")

    return {
        "detail": "MPPS status tag updated successfully",
        "service_request_id": str(service_request.external_id),
        "study_status": study_status,
        "tag_id": tag_config.id,
        "tag_uuid": str(tag_config.external_id),
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
        return {**cached, "external_id": dicom_study.external_id}

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

    if study_date_raw and study_time_raw:
        study_date = d_datetime_to_iso(study_date_raw, study_time_raw)
    elif study_date_raw:
        study_date = d_datetime_to_iso(study_date_raw)
    else:
        study_date = None

    cachable = {
        "study_uid": study_uid,
        "study_date": study_date,
        "study_description": study_description,
        "study_modalities": d_find(study, DICOM_TAG.StudyModalities.value),
        "study_series": series,
    }

    cache.set(key, cachable, timeout=60 * 60)
    return {**cachable, "external_id": dicom_study.external_id}


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
        study.save(
            update_fields=[
                "is_archived",
                "archive_reason",
                "archived_datetime",
                "archived_by",
                "deleted",
                "modified_date",
            ]
        )

    # A re-upload of this study has to link its new record, not reuse the cached link.
    rsr = study.radiology_service_request
    if rsr is not None and rsr.service_request_id is not None:
        cache.delete(DICOM_STUDY_LINK_CACHE_KEY_TEMPLATE.format(study.dicom_study_uid, rsr.service_request.external_id))
    return study
