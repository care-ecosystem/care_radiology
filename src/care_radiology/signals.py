from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from care.emr.models.service_request import ServiceRequest
from care.emr.resources.service_request.spec import SERVICE_REQUEST_CANCELLED_CHOICES

from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.tasks.create_radiology_note_thread import create_radiology_note_thread
from care_radiology.tasks.deactivate_radiology_service_request import deactivate_radiology_service_request

from care_radiology.settings import plugin_settings as settings


@receiver(post_save, sender=ServiceRequest)
def on_service_request_save(sender, instance, created, **kwargs):
    if instance.category != settings.CARE_RADIOLOGY_RADIOLOGY_CATEGORY:
        return

    service_request_id = instance.id

    if created:
        RadiologyServiceRequest.objects.get_or_create(service_request=instance)

        transaction.on_commit(
            lambda: create_radiology_note_thread.delay(
                service_request_id=service_request_id
            )
        )
        return

    if instance.status in SERVICE_REQUEST_CANCELLED_CHOICES:
        transaction.on_commit(
            lambda: deactivate_radiology_service_request.delay(
                service_request_id=service_request_id
            )
        )
