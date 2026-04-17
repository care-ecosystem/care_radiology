from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.models.study_report_audit import StudyReportAudit
from care_radiology.resources.study_report_audit.spec import StudyReportAuditListSpec


class StudyReportAuditViewSet(EMRModelViewSet):
    database_model = StudyReportAudit
    pydantic_model = None
    pydantic_read_model = StudyReportAuditListSpec
    pydantic_update_model = None
    pydantic_retrieve_model = StudyReportAuditListSpec

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["study_report__external_id"]
    ordering_fields = ["created_date"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("study_report", "created_by", "updated_by")

        study_report_id = self.request.query_params.get("study_report")
        if study_report_id:
            qs = qs.filter(study_report__external_id=study_report_id)

        return qs
