import time

import requests
from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.cache import cache

from care.emr.models.patient import Patient
from care_radiology.constants import (
    DICOM_STUDY_LAST_UPLOAD_KEY_TEMPLATE,
    DICOM_STUDY_PATIENT_SYNC_SCHEDULED_KEY_TEMPLATE,
)
from care_radiology.services.dicom_service import PacsPatientSyncError, move_study_to_patient
from care_radiology.settings import plugin_settings

logger = get_task_logger(__name__)


def _key_timeout():
    return plugin_settings.CARE_RADIOLOGY_PACS_PATIENT_SYNC_DELAY_SECONDS * 2 + 60


def schedule_move_study_to_care_patient(study_uid, patient_id):
    """
    The study is moved once its files stop arriving: a file
    stored after the move, still with its old Patient ID, would be rejected by the PACS.
    """
    timeout = _key_timeout()
    cache.set(DICOM_STUDY_LAST_UPLOAD_KEY_TEMPLATE.format(study_uid), time.time(), timeout=timeout)
    scheduled_key = DICOM_STUDY_PATIENT_SYNC_SCHEDULED_KEY_TEMPLATE.format(study_uid)
    if cache.add(scheduled_key, True, timeout=timeout):
        move_study_to_care_patient.apply_async(
            kwargs={"study_uid": study_uid, "patient_id": patient_id},
            countdown=plugin_settings.CARE_RADIOLOGY_PACS_PATIENT_SYNC_DELAY_SECONDS,
        )
    else:
        cache.touch(scheduled_key, timeout)


@shared_task(
    autoretry_for=(PacsPatientSyncError, requests.RequestException),
    retry_backoff=True,
    max_retries=5,
)
def move_study_to_care_patient(study_uid, patient_id):
    last_upload = cache.get(DICOM_STUDY_LAST_UPLOAD_KEY_TEMPLATE.format(study_uid))
    if last_upload is not None:
        remaining = last_upload + plugin_settings.CARE_RADIOLOGY_PACS_PATIENT_SYNC_DELAY_SECONDS - time.time()
        if remaining > 0:
            move_study_to_care_patient.apply_async(
                kwargs={"study_uid": study_uid, "patient_id": patient_id}, countdown=remaining
            )
            return False
    cache.delete(DICOM_STUDY_PATIENT_SYNC_SCHEDULED_KEY_TEMPLATE.format(study_uid))

    patient = Patient.objects.filter(id=patient_id).first()
    if patient is None:
        logger.warning("Patient %s not found, DICOM study %s not moved in PACS", patient_id, study_uid)
        return False
    return move_study_to_patient(study_uid, patient)
