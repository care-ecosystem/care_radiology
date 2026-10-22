from typing import Literal

from pydantic import UUID4, BaseModel

from care.emr.models.device import Device
from care.emr.models.location import FacilityLocation
from care.emr.resources.base import EMRResource


class WorklistDeviceSpec(EMRResource):
    __model__ = Device

    id: UUID4 | None = None
    name: str | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["name"] = obj.registered_name


class WorklistLocationSpec(EMRResource):
    __model__ = FacilityLocation

    id: UUID4 | None = None
    name: str | None = None
    devices: list[dict] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, devices=(), **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["devices"] = list(devices)


class DicomWorklistQuerySpec(BaseModel):
    modality: str | None = None
    created_date_after: str | None = None
    created_date_before: str | None = None


class WebhookMppsSpec(BaseModel):
    service_request_id: UUID4
    study_status: Literal["IN_PROGRESS", "COMPLETED", "CANCELLED"]
