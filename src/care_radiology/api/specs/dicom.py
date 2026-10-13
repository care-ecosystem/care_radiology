import datetime

from care.emr.resources.base import EMRResource
from care.users.models import User
from pydantic import UUID4, BaseModel, Field

from care_radiology.models.dicom_study import DicomStudy


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


class DicomStudyBaseSpec(EMRResource):
    __model__ = DicomStudy

    id: UUID4 | None = None
    study_uid: str
    created_by: dict | None = None
    updated_by: dict | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["study_uid"] = obj.dicom_study_uid
        for field in ("created_by", "updated_by"):
            user = getattr(obj, field)
            mapping[field] = DicomStudyUserSpec.serialize(user).to_json() if user else None


class DicomStudyArchiveStateSpec(DicomStudyBaseSpec):
    is_archived: bool
    archive_reason: str
    archived_datetime: datetime.datetime | None = None
    archived_by: dict | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["archived_by"] = DicomStudyUserSpec.serialize(obj.archived_by).to_json() if obj.archived_by else None


class DicomStudyReadSpec(DicomStudyArchiveStateSpec):
    study_date: str | None = None
    study_description: str | None = None
    study_modalities: list[str] = []
    study_series: list[dict] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, pacs_details=None):
        super().perform_extra_serialization(mapping, obj)
        mapping.update(pacs_details or {})


class DicomWorklistQuerySpec(BaseModel):
    modality: str | None = None
    from_date: str | None = Field(None, alias="from")
    to_date: str | None = Field(None, alias="to")
    facility_id: UUID4 = Field(alias="facility")
