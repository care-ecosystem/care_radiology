from django.db import models
from care.emr.models import EMRBaseModel


class RadiologyWebhookLogs(EMRBaseModel):
    raw_data = models.JSONField()
    type = models.CharField(max_length=50)
