from datetime import datetime
from typing import Annotated, Literal

from pydantic import UUID4, BaseModel, BeforeValidator

from care.emr.models.device import Device
from care.emr.models.location import FacilityLocation
from care.emr.resources.base import EMRResource
from care_radiology.utils.dicom import parse_date


class WorklistDeviceSpec(EMRResource):
    __model__ = Device

    id: UUID4 | None = None
    name: str | None = None
    ae_title: str | None = None
    modality: str | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["name"] = obj.registered_name
        machine = obj.metadata.get("machine") or {}
        mapping["ae_title"] = machine.get("ae_title")
        mapping["modality"] = machine.get("modality")


class WorklistLocationSpec(EMRResource):
    __model__ = FacilityLocation

    id: UUID4 | None = None
    name: str | None = None
    devices: list[dict] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, devices=(), **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["devices"] = list(devices)


WorklistDate = Annotated[datetime | None, BeforeValidator(parse_date)]


class DicomWorklistQuerySpec(BaseModel):
    device_id: str | None = None
    created_date_after: WorklistDate = None
    created_date_before: WorklistDate = None


class WebhookMppsSpec(BaseModel):
    service_request_id: UUID4
    study_status: Literal["IN_PROGRESS", "COMPLETED", "CANCELLED"]
