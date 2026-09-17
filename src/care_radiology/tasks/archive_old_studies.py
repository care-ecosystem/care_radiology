from datetime import timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone

from care_radiology.models.dicom_study import DicomStudy
from care_radiology.services.dicom_service import archive_study
from care_radiology.settings import plugin_settings

logger = get_task_logger(__name__)


@shared_task
def archive_old_dicom_studies():
    if not plugin_settings.CARE_RADIOLOGY_STUDY_AUTO_ARCHIVE_ENABLED:
        return 0

    auto_archive_days = plugin_settings.CARE_RADIOLOGY_STUDY_AUTO_ARCHIVE_DAYS
    threshold = timezone.now() - timedelta(days=auto_archive_days)
    studies = DicomStudy.objects.filter(is_archived=False, created_date__lte=threshold)

    count = 0
    for study in studies.iterator():
        archive_study(study, archive_reason=f"Auto-archived: older than {auto_archive_days} days")
        count += 1

    logger.info("Auto-archived %d DICOM studies older than %d days", count, auto_archive_days)
    return count
