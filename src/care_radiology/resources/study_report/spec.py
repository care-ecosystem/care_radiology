from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from care_radiology.models.study_report import StudyReport
from care_radiology.models.study_report_audit import StudyReportAudit
from care_radiology.models.modality_type import ModalityType
from care_radiology.models.body_part import BodyPart
from care_radiology.models.scan_protocol import ScanProtocol
from care_radiology.models.dicom_study import DicomStudy
from care.emr.models.patient import Patient
from care.emr.resources.patient.spec import PatientListSpec



class StudyReportCreateSpec(BaseModel):
    study: UUID
    modality: UUID
    body_part: UUID
    scan_protocol: UUID
    technique: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None

    def de_serialize(self) -> StudyReport:
        """Convert to StudyReport instance (resolve FKs)."""
        study = DicomStudy.objects.filter(external_id=self.study).first()
        modality = ModalityType.objects.filter(external_id=self.modality).first()
        body_part = BodyPart.objects.filter(external_id=self.body_part).first()
        scan_protocol = ScanProtocol.objects.filter(external_id=self.scan_protocol).first()

        if not all([study, modality, body_part, scan_protocol]):
            raise ValidationError("Invalid study/modality/body_part/scan_protocol IDs")

        # Check if StudyReport already exists for this study
        existing_report = StudyReport.objects.filter(study=study).first()

        if existing_report:
            old_values = {}
            new_values = {}

            def track(field, old, new):
                if old != new:
                    old_values[field] = str(old) if old is not None else None
                    new_values[field] = str(new) if new is not None else None

            track("Modality", existing_report.modality, modality)
            track("Body Part", existing_report.body_part, body_part)
            track("Scan Protocol", existing_report.scan_protocol, scan_protocol)
            track("Technique", existing_report.technique, self.technique)
            track("Findings", existing_report.findings, self.findings)
            track("Impression", existing_report.impression, self.impression)

            # Only log audit if something changed
            if old_values:
                StudyReportAudit.objects.create(
                    study_report=existing_report,
                    action="Updated",
                    field_name="Multiple",
                    old_value=old_values,
                    new_value=new_values,
                )
                # Update existing fields
                existing_report.modality = modality
                existing_report.body_part = body_part
                existing_report.scan_protocol = scan_protocol
                existing_report.technique = self.technique
                existing_report.findings = self.findings
                existing_report.impression = self.impression
                existing_report.last_modified_datetime = timezone.now()
                existing_report.save()
            return existing_report

        # ---------------- CREATE FLOW ----------------
        report = StudyReport.objects.create(
            study=study,
            modality=modality,
            body_part=body_part,
            scan_protocol=scan_protocol,
            technique=self.technique,
            findings=self.findings,
            impression=self.impression,
        )

        StudyReportAudit.objects.create(
            study_report=report,
            action="Created",
            field_name="All",
            old_value=None,
            new_value={
                "Modality": str(modality),
                "Body Part": str(body_part),
                "Scan Protocol": str(scan_protocol),
                "Technique": self.technique,
                "Findings": self.findings,
                "Impression": self.impression,
            },
        )

        return report

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
    modality_id: UUID
    body_part_id: UUID
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
            modality_id=obj.modality.external_id,
            body_part_id=obj.body_part.external_id,
            scan_protocol_id=obj.scan_protocol.external_id,
            study=getattr(obj.study, "study_name", None),
            modality=obj.modality.display_name,
            body_part=obj.body_part.display_name,
            scan_protocol=obj.scan_protocol.display_name,
            technique=obj.technique,
            findings=obj.findings,
            impression=obj.impression,
            created_datetime=obj.created_datetime.isoformat() if obj.created_datetime else None,
            last_modified_datetime=obj.last_modified_datetime.isoformat() if obj.last_modified_datetime else None,
            created_by=_serialize_lite_user(obj.created_by),
            updated_by=_serialize_lite_user(obj.updated_by),
        )

    # Add this for backward compatibility
    def to_json(self):
        """Make compatible with EMRModelViewSet expecting .to_json().."""
        try:
            return self.model_dump()
        except Exception:
            # fallback if using older Pydantic
            return self.json()
