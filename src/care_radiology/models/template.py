from django.db import models
from care.emr.models import EMRBaseModel
from care.users.models import User
from care_radiology.models.scan_protocol import ScanProtocol


class Template(EMRBaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="templates")
    modality = models.CharField(max_length=255)
    body_part = models.CharField(max_length=255)
    scan_protocol = models.ForeignKey(ScanProtocol, on_delete=models.CASCADE)
    technique = models.TextField(null=True, blank=True)
    findings = models.TextField(null=True, blank=True)
    impression = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Template: {self.modality} - {self.body_part}"
