from celery import Celery, current_app
from celery.schedules import crontab

from care_radiology.settings import plugin_settings
from care_radiology.tasks.archive_old_studies import archive_old_dicom_studies


@current_app.on_after_finalize.connect
def setup_periodic_tasks(sender: Celery, **kwargs):
    if plugin_settings.CARE_RADIOLOGY_STUDY_AUTO_ARCHIVE_ENABLED:
        sender.add_periodic_task(
            crontab(hour="1", minute="0"),
            archive_old_dicom_studies.s(),
            name="archive_old_dicom_studies",
        )
