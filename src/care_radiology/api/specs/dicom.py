import datetime

from pydantic import UUID4, BaseModel, Field

from care.emr.resources.base import EMRResource, cacheable, model_from_cache
from care.users.models import User
from care_radiology.models.dicom_study import DicomStudy


class DicomStudyLinkSpec(BaseModel):
    service_request_id: UUID4
    study_uid: str = Field(min_length=1)


class DicomStudyArchiveSpec(BaseModel):
    archive_reason: str = Field(min_length=1)


@cacheable(use_base_manager=True)
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
        if obj.created_by_id:
            mapping["created_by"] = model_from_cache(DicomStudyUserSpec, id=obj.created_by_id)
        if obj.updated_by_id:
            mapping["updated_by"] = model_from_cache(DicomStudyUserSpec, id=obj.updated_by_id)


class DicomStudyReadSpec(DicomStudyBaseSpec):
    study_date: str | None = None
    study_description: str | None = None
    study_modalities: list[str] = []
    study_series: list[dict] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, pacs_details, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        for field in ("study_date", "study_description", "study_modalities", "study_series"):
            mapping[field] = pacs_details[field]


class DicomStudyArchiveStateSpec(DicomStudyBaseSpec):
    is_archived: bool
    archive_reason: str
    archived_datetime: datetime.datetime | None = None
    archived_by: dict | None = None

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        if obj.archived_by_id:
            mapping["archived_by"] = model_from_cache(DicomStudyUserSpec, id=obj.archived_by_id)


class DicomStudyRetrieveSpec(DicomStudyReadSpec, DicomStudyArchiveStateSpec):
    pass


class DicomWorklistQuerySpec(BaseModel):
    modality: str | None = None
    from_date: str | None = Field(None, alias="from")
    to_date: str | None = Field(None, alias="to")
    facility_id: UUID4 = Field(alias="facility")
