from django.db import models
from care.emr.models import EMRBaseModel
from care.users.models import User
from care_radiology.models.modality_type import ModalityType
from care_radiology.models.body_part import BodyPart
from care_radiology.models.scan_protocol import ScanProtocol


class Template(EMRBaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="templates")
    modality = models.ForeignKey(ModalityType, on_delete=models.CASCADE)
    body_part = models.ForeignKey(BodyPart, on_delete=models.CASCADE)
    scan_protocol = models.ForeignKey(ScanProtocol, on_delete=models.CASCADE)
    technique = models.TextField(null=True, blank=True)
    findings = models.TextField(null=True, blank=True)
    impression = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Template: {self.modality.display_name} - {self.body_part.display_name}"
