# from celery import current_app
from celery.schedules import schedule
from config.celery_app import app
from care_radiology.tasks.sync_dicom_studies import sync_dicom_studies

@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        schedule(20.0),
        sync_dicom_studies.s(),
        name="radiology_sync_dicom_studies",
    )
