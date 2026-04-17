from django.db import models
from care.emr.models import EMRBaseModel


class ModalityType(EMRBaseModel):
    display_name = models.CharField(max_length=255, unique=True)
    coding = models.JSONField(default=list)  # [{coding_system, coding_code, coding_display}]

    def __str__(self):
        return self.display_name
