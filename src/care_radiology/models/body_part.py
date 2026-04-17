from django.db import models
from care.emr.models import EMRBaseModel
from care_radiology.models.modality_type import ModalityType


class BodyPart(EMRBaseModel):
    modality = models.ForeignKey(ModalityType, on_delete=models.CASCADE, related_name="body_parts")
    display_name = models.CharField(max_length=255)
    coding = models.JSONField(default=list)

    def __str__(self):
        return f"{self.display_name} ({self.modality.display_name})"
