from django.db import models
from care.emr.models import EMRBaseModel
from care_radiology.models.modality_type import ModalityType
from care_radiology.models.body_part import BodyPart


class ScanProtocol(EMRBaseModel):
    modality = models.ForeignKey(ModalityType, on_delete=models.CASCADE, related_name="scan_protocols")
    body_part = models.ForeignKey(BodyPart, on_delete=models.CASCADE, related_name="scan_protocols")
    display_name = models.CharField(max_length=255)
    coding = models.JSONField(default=list)

    def __str__(self):
        return f"{self.display_name} ({self.modality.display_name} - {self.body_part.display_name})"
