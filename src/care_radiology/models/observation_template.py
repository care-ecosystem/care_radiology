from django.db import models
from care.emr.models import EMRBaseModel
from care.facility.models import Facility


class ObservationTemplate(EMRBaseModel):
    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name="radiology_observation_templates"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    observation_definition = models.ForeignKey(
        "emr.ObservationDefinition",
        on_delete=models.CASCADE,
        related_name="radiology_templates",
    )
    activity_definition = models.ForeignKey(
        "emr.ActivityDefinition",
        on_delete=models.CASCADE,
        related_name="radiology_observation_templates",
        null=True,
        blank=True,
        default=None,
    )

    class Meta:
        indexes = [
            models.Index(fields=["observation_definition", "activity_definition"]),
        ]

    def __str__(self):
        return f"ObservationTemplate: {self.title}"


class ObservationTemplateData(models.Model):
    template = models.ForeignKey(
        ObservationTemplate, on_delete=models.CASCADE, related_name="data"
    )
    code = models.CharField(max_length=255)
    value = models.TextField()
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"ObservationTemplateData: {self.id} (template={self.template_id})"
