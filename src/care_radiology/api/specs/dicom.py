import datetime

from care.emr.resources.base import EMRResource
from care.users.models import User
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


class DicomStudyUserSpec(EMRResource):
    __model__ = User

    id: UUID4 | None = None
    username: str
    prefix: str | None = None
    first_name: str
    last_name: str
    suffix: str | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = str(obj.external_id)


class DicomStudyArchiveStateSpec(EMRResource):
    __model__ = DicomStudy

    id: UUID4 | None = None
    dicom_study_uid: str
    is_archived: bool
    archive_reason: str
    archived_datetime: datetime.datetime | None = None
    archived_by: DicomStudyUserSpec | None = None
    created_by: DicomStudyUserSpec | None = None
    updated_by: DicomStudyUserSpec | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        for field in ("created_by", "updated_by", "archived_by"):
            user = getattr(obj, field)
            mapping[field] = DicomStudyUserSpec.serialize(user).to_json() if user else None


class DicomWorklistQuerySpec(BaseModel):
    modality: str | None = None
    from_date: str | None = Field(None, alias="from")
    to_date: str | None = Field(None, alias="to")
    facility_id: UUID4 = Field(alias="facility")
