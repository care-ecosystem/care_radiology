from pydantic import UUID4, BaseModel, Field


class DicomWorklistQuerySpec(BaseModel):
    modality: str | None = None
    created_date_after: str | None = None
    created_date_before: str | None = None


class WebhookMppsSpec(BaseModel):
    service_request_id: UUID4
    study_status: str = Field(min_length=1)
