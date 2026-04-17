from django_filters.rest_framework import DjangoFilterBackend
from care.security.authorization.base import PermissionDeniedError
from rest_framework.filters import OrderingFilter
from rest_framework.exceptions import PermissionDenied
from care.emr.api.viewsets.base import EMRModelViewSet
from care_radiology.models.study_report import StudyReport
from care_radiology.resources.study_report.spec import (
    StudyReportCreateSpec,
    StudyReportListSpec,
)
from care.security.authorization import AuthorizationController


class StudyReportViewSet(EMRModelViewSet):
    """CRUD API for StudyReport"""

    database_model = StudyReport
    pydantic_model = StudyReportCreateSpec
    pydantic_read_model = StudyReportListSpec
    pydantic_update_model = None
    pydantic_retrieve_model = StudyReportListSpec

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["study__external_id"]
    ordering_fields = ["created_date", "modified_date"]

    def verify_report_permission(self, type):
        if not AuthorizationController.call(
            "can_read_radiology_report" if type == 'read' else "can_write_radiology_report",
            self.request.user,
        ):
            raise PermissionDenied(f"You do not have permission to {'view' if type == 'read' else 'write'} this report")

    def authorize_create(self, request_obj):
        self.verify_report_permission('write')
        pass

    def authorize_update(self, request_obj, model_instance):
        self.verify_report_permission('write')
        pass

    def authorize_destroy(self, instance):
        self.verify_report_permission('write')
        pass

    def get_queryset(self):
        self.verify_report_permission('read')
        qs = (
            super()
            .get_queryset()
            .select_related("study", "modality", "body_part", "scan_protocol")
            .order_by("-created_date")
        )

        # ★ Manual support for ?study=<uuid> (frontend uses this)
        study_id = self.request.query_params.get("study")
        if study_id:
            qs = qs.filter(study__external_id=study_id)

        return qs

    def perform_create(self, instance):
        from care_radiology.models.study_report_audit import StudyReportAudit

        user = self.request.user

        StudyReportAudit.objects.filter(
            study_report=instance,
            created_by__isnull=True,
        ).update(
            created_by=user,
            updated_by=user,
        )
        super().perform_create(instance)
