from care.emr.models import EMRBaseModel
from care.emr.models.service_request import ServiceRequest
from django.db import models


class RadiologyServiceRequest(EMRBaseModel):
    service_request = models.ForeignKey(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="radiology_service_requests",
        null=True,
        unique=True,
    )
    raw_data = models.JSONField(default=dict)
