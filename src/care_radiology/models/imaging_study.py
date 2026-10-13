from django.db import models

from care.utils.models.base import BaseModel

from care.emr.models.encounter import Encounter
from care.emr.models.service_request import ServiceRequest


class ImagingStudyStatus(models.TextChoices):
    ACTIVE = "ACTIVE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ImagingStudy(BaseModel):
    service_request = models.OneToOneField(
        ServiceRequest,
        on_delete=models.CASCADE,
        related_name="imaging_study",
        null=True,
    )
    encounter = models.ForeignKey(
        Encounter,
        on_delete=models.CASCADE,
        related_name="imaging_studies",
    )
    accession_number = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=ImagingStudyStatus.choices,
        default=ImagingStudyStatus.ACTIVE,
    )
