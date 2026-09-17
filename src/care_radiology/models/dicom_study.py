from care.emr.models import EMRBaseModel
from care.emr.models.patient import Patient
from django.db import models

from care_radiology.models.radiology_service_request import RadiologyServiceRequest


class DicomStudy(EMRBaseModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="dicom_studies")
    radiology_service_request = models.ForeignKey(
        RadiologyServiceRequest,
        on_delete=models.CASCADE,
        related_name="studies",
        null=True,
    )
    dicom_study_uid = models.CharField(max_length=500)

    is_archived = models.BooleanField(default=False)
    archive_reason = models.TextField(blank=True, default="")
    archived_datetime = models.DateTimeField(blank=True, null=True)
    archived_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="archived_dicom_studies",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["patient", "dicom_study_uid"], name="unique_patient_study_uid")]
