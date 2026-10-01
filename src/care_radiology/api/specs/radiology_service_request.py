from care.emr.resources.base import EMRResource
from pydantic import UUID4

from care_radiology.models.radiology_service_request import RadiologyServiceRequest


class RadiologyServiceRequestReadSpec(EMRResource):
    __model__ = RadiologyServiceRequest

    id: UUID4 | None = None
    status: str
    accession_number: str | None = None
