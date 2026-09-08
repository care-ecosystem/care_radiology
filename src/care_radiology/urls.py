from django.conf import settings
from django.shortcuts import HttpResponse
from django.urls import path
from rest_framework.routers import DefaultRouter, SimpleRouter

from care_radiology.api.viewsets.dicom import DicomViewSet
from care_radiology.api.viewsets.webhooks import WebhookViewSet
from care_radiology.api.viewsets.observation_template import ObservationTemplateViewSet


def healthy(request):
    return HttpResponse("OK")


router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("webhooks", WebhookViewSet, basename="radiology_webhooks")
router.register("dicom", DicomViewSet, basename="radiology_dicom")
router.register(
    "observation_template",
    ObservationTemplateViewSet,
    basename="radiology_observation_template",
)

urlpatterns = [
    path("health", healthy),
] + router.urls
