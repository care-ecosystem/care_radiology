from pydantic import UUID4, BaseModel, Field, model_validator


class WebhookStudySpec(BaseModel):
    service_request_id: UUID4 | None = None
    accession_number: str | None = None
    patient_id: str | None = None
    study_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_one_lookup(self):
        if not (self.service_request_id or self.accession_number or self.patient_id):
            raise ValueError("One of service_request_id, accession_number or patient_id is required")
        return self


class WebhookMppsSpec(BaseModel):
    service_request_id: UUID4
    study_status: str = Field(min_length=1)
