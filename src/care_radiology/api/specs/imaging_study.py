from care.emr.resources.base import EMRResource
from care.emr.resources.encounter.spec import EncounterSpecBase
from care.emr.resources.service_request.spec import BaseServiceRequestSpec, ServiceRequestRetrieveSpec
from pydantic import UUID4

from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus


class ImagingStudyReadSpec(EMRResource):
    __model__ = ImagingStudy

    id: UUID4 | None = None
    status: ImagingStudyStatus
    accession_number: str | None = None
    encounter: dict
    service_request: dict | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        mapping["encounter"] = EncounterSpecBase.serialize(obj.encounter).to_json()
        if obj.service_request:
            mapping["service_request"] = BaseServiceRequestSpec.serialize(obj.service_request).to_json()


class ImagingStudyRetrieveSpec(ImagingStudyReadSpec):
    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        if obj.service_request:
            mapping["service_request"] = ServiceRequestRetrieveSpec.serialize(obj.service_request).model_dump(
                mode="json", exclude={"meta", "encounter", "specimens", "tags"}
            )


class ImagingStudyUpdateSpec(EMRResource):
    __model__ = ImagingStudy

    status: ImagingStudyStatus
