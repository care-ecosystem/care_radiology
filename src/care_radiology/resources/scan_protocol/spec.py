from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from care_radiology.models.scan_protocol import ScanProtocol
from care_radiology.models.modality_type import ModalityType
from care_radiology.models.body_part import BodyPart
from rest_framework.exceptions import ValidationError


class ScanProtocolCoding(BaseModel):
    coding_system: str
    coding_code: str
    coding_display: str


class ScanProtocolListSpec(BaseModel):
    external_id: UUID
    display_name: str
    modality_id: UUID
    modality: str
    body_part_id: UUID
    body_part: str
    coding: list[ScanProtocolCoding] | None = None

    @classmethod
    def serialize(cls, obj: ScanProtocol):
        return cls(
            external_id=obj.external_id,
            display_name=obj.display_name,
            modality_id=obj.modality.external_id if obj.modality else None,
            modality=obj.modality.display_name if obj.modality else None,
            body_part_id=obj.body_part.external_id if obj.body_part else None,
            body_part=obj.body_part.display_name if obj.body_part else None,
            coding=obj.coding or [],
        )

    def to_json(self):
        return self.model_dump()


class ScanProtocolCreateSpec(BaseModel):
    modality: UUID  # external_id of ModalityType
    body_part: UUID  # external_id of BodyPart
    display_name: str
    coding: List[ScanProtocolCoding]

    def de_serialize(self) -> ScanProtocol:
        """Create or revive a ScanProtocol entry."""
        modality = ModalityType.objects.filter(external_id=self.modality).first()
        if not modality:
            raise ValidationError(f"Invalid modality id: {self.modality}")

        body_part = BodyPart.objects.filter(external_id=self.body_part).first()
        if not body_part:
            raise ValidationError(f"Invalid body part id: {self.body_part}")

        existing = ScanProtocol.objects.filter(
            display_name=self.display_name, modality=modality, body_part=body_part
        ).first()

        if existing:
            if existing.deleted:
                existing.deleted = False
                existing.coding = [c.model_dump() for c in self.coding]
                existing.save(update_fields=["deleted", "coding", "modified_date"])
                existing._state.adding = False
                return existing
            raise ValidationError(
                f"Scan protocol '{self.display_name}' already exists for "
                f"{modality.display_name} - {body_part.display_name}."
            )

        obj = ScanProtocol(
            modality=modality,
            body_part=body_part,
            display_name=self.display_name,
            coding=[c.model_dump() for c in self.coding],
        )
        return obj


class ScanProtocolUpdateSpec(BaseModel):
    modality: Optional[UUID] = None
    body_part: Optional[UUID] = None
    display_name: Optional[str] = None
    coding: Optional[List[ScanProtocolCoding]] = None

    def de_serialize(self, obj: ScanProtocol, **kwargs) -> ScanProtocol:
        """Update an existing ScanProtocol model instance."""
        if self.modality is not None:
            modality = ModalityType.objects.filter(external_id=self.modality).first()
            if not modality:
                raise ValidationError(f"Invalid modality id: {self.modality}")
            obj.modality = modality

        if self.body_part is not None:
            body_part = BodyPart.objects.filter(external_id=self.body_part).first()
            if not body_part:
                raise ValidationError(f"Invalid body part id: {self.body_part}")
            obj.body_part = body_part

        if self.display_name is not None:
            obj.display_name = self.display_name

        if self.coding is not None:
            obj.coding = [c.model_dump() for c in self.coding]

        return obj
