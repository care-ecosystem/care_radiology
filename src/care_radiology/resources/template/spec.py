from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from care_radiology.models.template import Template
from care_radiology.models.modality_type import ModalityType
from care_radiology.models.body_part import BodyPart
from care_radiology.models.scan_protocol import ScanProtocol
from django.contrib.auth import get_user_model

User = get_user_model()


class TemplateCreateSpec(BaseModel):
    modality: UUID
    body_part: UUID
    scan_protocol: UUID
    technique: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None

    def de_serialize(self, user) -> Template:
        """Create or update a Template for the same user + modality + bodypart + scan_protocol."""

        modality = ModalityType.objects.filter(external_id=self.modality).first()
        body_part = BodyPart.objects.filter(external_id=self.body_part).first()
        scan_protocol = ScanProtocol.objects.filter(external_id=self.scan_protocol).first()

        if not all([modality, body_part, scan_protocol]):
            raise ValidationError("Invalid modality/body_part/scan_protocol IDs")

        # Check if template already exists for same user + modality + body_part + scan_protocol
        existing_template = Template.objects.filter(
            user=user,
            modality=modality,
            body_part=body_part,
            scan_protocol=scan_protocol,
        ).first()

        if existing_template:
            existing_template.technique = self.technique
            existing_template.findings = self.findings
            existing_template.impression = self.impression
            existing_template.modified_date = timezone.now()
            existing_template.save()
            return existing_template
        else:
            return Template(
                user=user,
                modality=modality,
                body_part=body_part,
                scan_protocol=scan_protocol,
                technique=self.technique,
                findings=self.findings,
                impression=self.impression,
            )


class TemplateListSpec(BaseModel):
    external_id: UUID
    modality_id: UUID
    body_part_id: UUID
    scan_protocol_id: UUID
    modality: str
    body_part: str
    scan_protocol: str
    technique: Optional[str]
    findings: Optional[str]
    impression: Optional[str]

    @classmethod
    def serialize(cls, obj: Template):
        return cls(
            external_id=obj.external_id,
            modality_id=obj.modality.external_id,
            body_part_id=obj.body_part.external_id,
            scan_protocol_id=obj.scan_protocol.external_id,
            modality=obj.modality.display_name,
            body_part=obj.body_part.display_name,
            scan_protocol=obj.scan_protocol.display_name,
            technique=obj.technique,
            findings=obj.findings,
            impression=obj.impression,
        )

    def to_json(self):
        """Support EMRModelViewSet compatibility"""
        try:
            return self.model_dump()
        except Exception:
            return self.json()
