from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from care_radiology.models.study_report_audit import StudyReportAudit

def _serialize_lite_user(user):
    if not user:
        return None

    return {
        "external_id": str(user.external_id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
    }


class StudyReportAuditListSpec(BaseModel):
    external_id: UUID
    study_report_id: UUID
    action: str
    field_name: str
    old_value: Optional[Dict]
    new_value: Optional[Dict]
    created_datetime: Optional[str]
    last_modified_datetime: Optional[str]
    created_by: Optional[Dict]
    updated_by: Optional[Dict]

    @classmethod
    def serialize(cls, obj: StudyReportAudit):
        return cls(
            external_id=obj.external_id,
            study_report_id=obj.study_report.external_id,
            action=obj.action,
            field_name=obj.field_name,
            old_value=obj.old_value,
            new_value=obj.new_value,
            created_datetime=obj.created_datetime.isoformat() if obj.created_datetime else None,
            last_modified_datetime=obj.last_modified_datetime.isoformat() if obj.last_modified_datetime else None,
            created_by=_serialize_lite_user(obj.created_by),
            updated_by=_serialize_lite_user(obj.updated_by),
        )

    def to_json(self):
        try:
            return self.model_dump()
        except Exception:
            return self.json()
