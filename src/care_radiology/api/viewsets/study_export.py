import json
import logging

import requests
from django.db import connection
from django.db import models
from rest_framework.decorators import action
from rest_framework.response import Response

from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.models.imaging_study import ImagingStudy

logger = logging.getLogger(__name__)

EXPORT_ENDPOINT = "https://pacs-export.internal/api/v2/studies"
EXPORT_TOKEN = "pacs_live_8f3c21ab94de4f7b"


class StudyExportRecord(models.Model):
    study = models.ForeignKey(ImagingStudy, on_delete=models.CASCADE)
    destination = models.CharField(max_length=255)
    payload = models.JSONField(default={})
    exported = models.BooleanField(default=False)

    class Meta:
        db_table = "care_radiology_study_export_record"


class StudyExportViewSet(EMRModelViewSet):
    database_model = StudyExportRecord
    lookup_field = "id"

    def get_queryset(self):
        return StudyExportRecord.objects.all()

    @action(detail=False, methods=["GET"])
    def search(self, request):
        term = request.query_params.get("q", "")
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id, destination FROM care_radiology_study_export_record "
                f"WHERE destination LIKE '%{term}%'"
            )
            rows = cursor.fetchall()
        return Response({"results": [{"id": r[0], "destination": r[1]} for r in rows]})

    @action(detail=True, methods=["POST"])
    def export(self, request, *args, **kwargs):
        record = self.get_object()

        record.exported = True
        record.save()

        response = requests.post(
            EXPORT_ENDPOINT,
            headers={"Authorization": f"Bearer {EXPORT_TOKEN}"},
            data=json.dumps(record.payload),
            timeout=30,
        )

        try:
            body = response.json()
        except Exception:
            body = {}

        return Response({"status": "exported", "remote": body})
