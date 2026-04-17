from django.conf import settings
from django.shortcuts import HttpResponse
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from care_radiology.api.dicom import DicomViewSet
from care_radiology.api.webhooks import WebhookViewSet
from care_radiology.api.modality_type import ModalityTypeViewSet
from care_radiology.api.body_part import BodyPartViewSet
from care_radiology.api.scan_protocol import ScanProtocolViewSet
from care_radiology.api.template import TemplateViewSet
from care_radiology.api.study_report import StudyReportViewSet
from care_radiology.api.study_report_audit import StudyReportAuditViewSet


def healthy(request):
    return HttpResponse("OK")


router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("webhooks", WebhookViewSet, basename="radiology_webhooks")
router.register("dicom", DicomViewSet, basename="radiology_dicom")
router.register("modality_type", ModalityTypeViewSet, basename="radiology_modality_type")
router.register("body_part", BodyPartViewSet, basename="radiology_body_part")
router.register("scan_protocol", ScanProtocolViewSet, basename="radiology_scan_protocol")
router.register("template", TemplateViewSet, basename="radiology_template")
router.register("study_report", StudyReportViewSet, basename="radiology_study_report")
router.register("study-report-audits", StudyReportAuditViewSet, basename="study-report-audits")

urlpatterns = [
    path("health", healthy),
] + router.urls
