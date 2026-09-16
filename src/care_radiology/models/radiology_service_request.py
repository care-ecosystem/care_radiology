from care.emr.models import EMRBaseModel
from care.emr.models.service_request import ServiceRequest
from django.db import models


class RadiologyServiceRequestStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RadiologyServiceRequest(EMRBaseModel):
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="radiology_service_requests",
        null=True,
        unique=True,
    )
    raw_data = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20,
        choices=RadiologyServiceRequestStatus.choices,
        default=RadiologyServiceRequestStatus.ACTIVE,
    )
