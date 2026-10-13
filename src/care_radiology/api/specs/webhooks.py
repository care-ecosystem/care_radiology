from pydantic import UUID4, BaseModel, Field


class WebhookMppsSpec(BaseModel):
    service_request_id: UUID4
    study_status: str = Field(min_length=1)
