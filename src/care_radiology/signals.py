from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from care.emr.models.service_request import ServiceRequest

from care_radiology.tasks.create_radiology_note_thread import create_radiology_note_thread

from care_radiology.settings import plugin_settings as settings


@receiver(post_save, sender=ServiceRequest)
def on_service_request_save(sender, instance, created, **kwargs):
    if not created:
        return

    if instance.category != settings.CARE_RADIOLOGY_RADIOLOGY_CATEGORY:
        return

    transaction.on_commit(
        lambda: create_radiology_note_thread.delay(
            service_request_id=instance.id
        )
    )
