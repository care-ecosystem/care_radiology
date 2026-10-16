from django.db import models

from care.emr.models import EMRBaseModel
from care_radiology.models.imaging_study import ImagingStudy


class DicomStudy(EMRBaseModel):
    imaging_study = models.ForeignKey(ImagingStudy, on_delete=models.CASCADE, related_name="studies")
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
    number_of_series = models.PositiveIntegerField(null=True, blank=True)
    number_of_instances = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["imaging_study", "dicom_study_uid"],
                condition=models.Q(is_archived=False),
                name="unique_imaging_study_active_study_uid",
            )
        ]
