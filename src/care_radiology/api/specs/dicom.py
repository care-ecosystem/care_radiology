from pydantic import UUID4, BaseModel, Field, model_validator


class DicomStudyLinkSpec(BaseModel):
    service_request_id: UUID4
    study_uid: str = Field(min_length=1)


class DicomStudiesQuerySpec(BaseModel):
    encounter_id: UUID4 | None = Field(None, alias="encounterId")
    service_request_id: UUID4 | None = Field(None, alias="serviceRequestId")

    @model_validator(mode="after")
    def require_one_scope(self):
        if not self.encounter_id and not self.service_request_id:
            raise ValueError("Either encounterId or serviceRequestId is required")
        return self
