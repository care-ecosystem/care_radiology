from celery import shared_task
from celery.utils.log import get_task_logger

from care_radiology.services.dicom_service import (
    PacsDeleteError,
    cleanup_failed_upload,
    release_failed_upload_claim,
)

logger = get_task_logger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=1)
def cleanup_failed_pacs_upload(self, study_uid, sop_instance_uid, claim_key, token):
    """
    Started as soon as an upload to the PACS fails or times out. Retried while the PACS cannot be reached; once
    the retries run out, or on any other error, the claim is released anyway, so the file can be uploaded again.
    """
    try:
        cleanup_failed_upload(study_uid, sop_instance_uid, claim_key, token)
    except Exception as e:
        if isinstance(e, PacsDeleteError) and self.request.retries < self.max_retries:
            raise self.retry(exc=e) from e
        logger.exception(
            "Could not clean up the failed upload of %s (study %s), releasing its claim",
            sop_instance_uid,
            study_uid,
        )
        release_failed_upload_claim(claim_key, token)
