from care.emr.resources.base import EMRResource
from pydantic import UUID4

from care_radiology.models.imaging_study import ImagingStudy


class ImagingStudyReadSpec(EMRResource):
    __model__ = ImagingStudy

    id: UUID4 | None = None
    status: str
    accession_number: str | None = None
