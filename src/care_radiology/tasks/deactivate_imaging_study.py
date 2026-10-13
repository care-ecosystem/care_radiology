import logging

from care.emr.models.service_request import ServiceRequest
from celery import shared_task
from django.db import transaction

from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus
from care_radiology.services.dicom_service import archive_study

logger = logging.getLogger(__name__)


@shared_task
@transaction.atomic
def deactivate_imaging_study(service_request_id: str):
    try:
        service_request = ServiceRequest.objects.get(id=service_request_id)
    except ServiceRequest.DoesNotExist:
        logger.error("ServiceRequest with id %s not found.", service_request_id)
        return

    try:
        imaging_study = service_request.imaging_study
    except ImagingStudy.DoesNotExist:
        return

    if imaging_study.status != ImagingStudyStatus.CANCELLED:
        imaging_study.status = ImagingStudyStatus.CANCELLED
        imaging_study.save(update_fields=["status"])

    for study in imaging_study.studies.filter(is_archived=False):
        archive_study(study, archive_reason=f"Service request status: {service_request.status}")
