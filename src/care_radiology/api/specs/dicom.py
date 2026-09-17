import datetime

from care.emr.resources.base import EMRResource, model_from_cache
from care.emr.resources.user.spec import UserSpec
from pydantic import UUID4, BaseModel, Field, model_validator

from care_radiology.models.dicom_study import DicomStudy


class DicomStudyLinkSpec(BaseModel):
    service_request_id: UUID4
    study_uid: str = Field(min_length=1)


class DicomStudiesQuerySpec(BaseModel):
    encounter_id: UUID4 | None = Field(None, alias="encounterId")
    service_request_id: UUID4 | None = Field(None, alias="serviceRequestId")
    include_archived: bool = Field(False, alias="includeArchived")

    @model_validator(mode="after")
    def require_one_scope(self):
        if not self.encounter_id and not self.service_request_id:
            raise ValueError("Either encounterId or serviceRequestId is required")
        return self


class DicomStudyArchiveSpec(BaseModel):
    archive_reason: str = Field(min_length=1)


class DicomStudyArchiveStateSpec(EMRResource):
    __model__ = DicomStudy

    id: UUID4 | None = None
    dicom_study_uid: str
    is_archived: bool
    archive_reason: str
    archived_datetime: datetime.datetime | None = None
    archived_by: UserSpec | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        if obj.archived_by_id:
            mapping["archived_by"] = model_from_cache(UserSpec, id=obj.archived_by_id)


class DicomWorklistQuerySpec(BaseModel):
    modality: str | None = None
    from_date: str | None = Field(None, alias="from")
    to_date: str | None = Field(None, alias="to")
    facility_id: UUID4 = Field(alias="facility")
