from django.db import models
from care.emr.models import EMRBaseModel


class ScanProtocol(EMRBaseModel):
    modality = models.CharField(max_length=255)
    body_part = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    coding = models.JSONField(default=list)

    def __str__(self):
        return f"{self.display_name} ({self.modality} - {self.body_part})"
