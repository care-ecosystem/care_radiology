from django.db import models
from django.utils import timezone
from care.emr.models import EMRBaseModel
from care_radiology.models.study_report import StudyReport

class StudyReportAudit(EMRBaseModel):
    study_report = models.ForeignKey(
        StudyReport, on_delete=models.CASCADE, related_name="audits"
    )
    action = models.CharField(max_length=20)  # CREATED, UPDATED
    field_name = models.CharField(max_length=100)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    created_datetime = models.DateTimeField(default=timezone.now)
    last_modified_datetime = models.DateTimeField(auto_now=True)


    class Meta:
        ordering = ["-created_datetime"]  # uses BaseModel timestamps
