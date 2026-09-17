import logging

from care.emr.models.service_request import ServiceRequest
from celery import shared_task

from care_radiology.models.radiology_service_request import RadiologyServiceRequest, RadiologyServiceRequestStatus
from care_radiology.services.dicom_service import archive_study

logger = logging.getLogger(__name__)


@shared_task
def deactivate_radiology_service_request(service_request_id: str):
    try:
        service_request = ServiceRequest.objects.get(id=service_request_id)
    except ServiceRequest.DoesNotExist:
        logger.error("ServiceRequest with id %s not found.", service_request_id)
        return

    try:
        rsr = service_request.radiology_service_requests
    except RadiologyServiceRequest.DoesNotExist:
        return

    if rsr.status != RadiologyServiceRequestStatus.CANCELLED:
        rsr.status = RadiologyServiceRequestStatus.CANCELLED
        rsr.save(update_fields=["status"])

    for study in rsr.studies.filter(is_archived=False):
        archive_study(study, archive_reason=f"Service request status: {service_request.status}")
