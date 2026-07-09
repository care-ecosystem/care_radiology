from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from care_radiology.models.scan_protocol import ScanProtocol
from rest_framework.exceptions import ValidationError


class ScanProtocolCoding(BaseModel):
    coding_system: str
    coding_code: str
    coding_display: str


class ScanProtocolListSpec(BaseModel):
    external_id: UUID
    display_name: str
    modality: str
    body_part: str
    coding: list[ScanProtocolCoding] | None = None

    @classmethod
    def serialize(cls, obj: ScanProtocol):
        return cls(
            external_id=obj.external_id,
            display_name=obj.display_name,
            modality=obj.modality,
            body_part=obj.body_part,
            coding=obj.coding or [],
        )

    def to_json(self):
        return self.model_dump()


class ScanProtocolCreateSpec(BaseModel):
    modality: str
    body_part: str
    display_name: str
    coding: List[ScanProtocolCoding]

    def de_serialize(self) -> ScanProtocol:
        if not self.display_name:
            raise ValidationError("Scan Protocol is required")

        if not self.modality:
            raise ValidationError("Modality is required")

        if not self.body_part:
            raise ValidationError("Body part is required")

        existing = ScanProtocol.objects.filter(
            display_name=self.display_name, modality=self.modality, body_part=self.body_part
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
                f"{self.modality} - {self.body_part}."
            )

        return ScanProtocol(
            modality=self.modality,
            body_part=self.body_part,
            display_name=self.display_name,
            coding=[c.model_dump() for c in self.coding],
        )


class ScanProtocolUpdateSpec(BaseModel):
    modality: Optional[str] = None
    body_part: Optional[str] = None
    display_name: Optional[str] = None
    coding: Optional[List[ScanProtocolCoding]] = None

    def de_serialize(self, obj: ScanProtocol, **kwargs) -> ScanProtocol:
        if self.modality is not None:
            obj.modality = self.modality

        if self.body_part is not None:
            obj.body_part = self.body_part

        if self.display_name is not None:
            obj.display_name = self.display_name

        if self.coding is not None:
            obj.coding = [c.model_dump() for c in self.coding]

        return obj
