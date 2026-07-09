from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from care_radiology.models.study_report import StudyReport
from care_radiology.models.scan_protocol import ScanProtocol
from care_radiology.models.dicom_study import DicomStudy
from care.emr.resources.patient.spec import PatientListSpec


class StudyReportCreateSpec(BaseModel):
    study: UUID
    modality: str
    body_part: str
    scan_protocol: UUID
    technique: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None

    def de_serialize(self) -> StudyReport:
        study = DicomStudy.objects.filter(external_id=self.study).first()
        scan_protocol = ScanProtocol.objects.filter(external_id=self.scan_protocol).first()

        if not all([study, scan_protocol]):
            raise ValidationError("Invalid study/scan_protocol IDs")

        if not self.modality:
            raise ValidationError("Modality is required")

        if not self.body_part:
            raise ValidationError("Body part is required")

        return StudyReport(
            study=study,
            modality=self.modality,
            body_part=self.body_part,
            scan_protocol=scan_protocol,
            technique=self.technique,
            findings=self.findings,
            impression=self.impression,
        )


class StudyReportUpdateSpec(BaseModel):
    modality: Optional[str] = None
    body_part: Optional[str] = None
    scan_protocol: Optional[UUID] = None
    technique: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None

    def de_serialize(self, obj: StudyReport, partial: bool = False) -> StudyReport:
        modality = self.modality if self.modality is not None else obj.modality
        body_part = self.body_part if self.body_part is not None else obj.body_part
        scan_protocol = ScanProtocol.objects.filter(external_id=self.scan_protocol).first() if self.scan_protocol else obj.scan_protocol

        old_values = {}
        new_values = {}

        def track(field, old, new):
            if old != new:
                old_values[field] = str(old) if old is not None else None
                new_values[field] = str(new) if new is not None else None

        track("Modality", obj.modality, modality)
        track("Body Part", obj.body_part, body_part)
        track("Scan Protocol", obj.scan_protocol, scan_protocol)

        technique = self.technique if (self.technique is not None or not partial) else obj.technique
        findings = self.findings if (self.findings is not None or not partial) else obj.findings
        impression = self.impression if (self.impression is not None or not partial) else obj.impression

        track("Technique", obj.technique, technique)
        track("Findings", obj.findings, findings)
        track("Impression", obj.impression, impression)

        obj.modality = modality
        obj.body_part = body_part
        obj.scan_protocol = scan_protocol
        obj.technique = technique
        obj.findings = findings
        obj.impression = impression
        obj.last_modified_datetime = timezone.now()

        obj._audit_diff = (old_values, new_values)  # noqa: SLF001

        return obj


def _serialize_lite_user(user):
    if not user:
        return None

    return {
        "external_id": str(user.external_id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
    }


class StudyReportListSpec(BaseModel):
    external_id: UUID
    study_id: UUID
    patient_id: UUID
    patient: Optional[Dict] = None
    scan_protocol_id: UUID
    study: Optional[str] = None
    modality: str
    body_part: str
    scan_protocol: str
    technique: Optional[str]
    findings: Optional[str]
    impression: Optional[str]
    created_datetime: Optional[str]
    last_modified_datetime: Optional[str]
    created_by: Optional[Dict]
    updated_by: Optional[Dict]

    @classmethod
    def serialize(cls, obj: StudyReport):
        return cls(
            external_id=obj.external_id,
            study_id=obj.study.external_id,
            patient_id=obj.study.patient.external_id,
            patient=PatientListSpec.serialize(obj.study.patient).to_json(),
            scan_protocol_id=obj.scan_protocol.external_id,
            study=getattr(obj.study, "study_name", None),
            modality=obj.modality,
            body_part=obj.body_part,
            scan_protocol=obj.scan_protocol.display_name,
            technique=obj.technique,
            findings=obj.findings,
            impression=obj.impression,
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
