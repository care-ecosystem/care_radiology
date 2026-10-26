from django.conf import settings
from django.shortcuts import HttpResponse
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from care_radiology.api.viewsets.dicom import DicomViewSet
from care_radiology.api.viewsets.external import FacilityExternalViewSet
from care_radiology.api.viewsets.imaging_study import ImagingStudyViewSet
from care_radiology.api.viewsets.observation_template import ObservationTemplateViewSet


def healthy(request):
    return HttpResponse("OK")


router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("dicom", DicomViewSet, basename="radiology_dicom")
router.register(
    "observation_result_template",
    ObservationTemplateViewSet,
    basename="radiology_observation_result_template",
)
router.register(
    r"facility/(?P<facility_external_id>[^/.]+)/external",
    FacilityExternalViewSet,
    basename="radiology_external",
)
router.register(
    r"patient/(?P<patient_external_id>[^/.]+)/imaging_study",
    ImagingStudyViewSet,
    basename="imaging_study",
)

urlpatterns = [
    path("health", healthy),
] + router.urls
