from django.db import models
from django.utils import timezone
from care.emr.models import EMRBaseModel
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.modality_type import ModalityType
from care_radiology.models.body_part import BodyPart
from care_radiology.models.scan_protocol import ScanProtocol


class StudyReport(EMRBaseModel):
    study = models.ForeignKey(DicomStudy, on_delete=models.CASCADE, related_name="study_reports")
    modality = models.ForeignKey(ModalityType, on_delete=models.CASCADE)
    body_part = models.ForeignKey(BodyPart, on_delete=models.CASCADE)
    scan_protocol = models.ForeignKey(ScanProtocol, on_delete=models.CASCADE)
    technique = models.TextField(null=True, blank=True)
    findings = models.TextField(null=True, blank=True)
    impression = models.TextField(null=True, blank=True)
    created_datetime = models.DateTimeField(default=timezone.now)
    last_modified_datetime = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Report for Study: {self.study.study_name}"
