from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from care_radiology.models.body_part import BodyPart
from care_radiology.models.modality_type import ModalityType
from rest_framework.exceptions import ValidationError


class BodyPartCoding(BaseModel):
    coding_system: str
    coding_code: str
    coding_display: str


class BodyPartListSpec(BaseModel):
    external_id: UUID
    display_name: str
    modality_id: UUID
    modality: str
    coding: list[BodyPartCoding] | None = None

    @classmethod
    def serialize(cls, obj: BodyPart):
        return cls(
            external_id=obj.external_id,
            display_name=obj.display_name,
            modality_id=obj.modality.external_id if obj.modality else None,
            modality=obj.modality.display_name if obj.modality else None,
            coding=obj.coding or [],
        )

    def to_json(self):
        return self.model_dump()


class BodyPartCreateSpec(BaseModel):
    modality: UUID  # pass modality external_id
    display_name: str
    coding: List[BodyPartCoding]

    def de_serialize(self) -> BodyPart:
        """Create or revive a BodyPart entry."""
        modality = ModalityType.objects.filter(external_id=self.modality).first()
        if not modality:
            raise ValidationError(f"Invalid modality id: {self.modality}")

        existing = BodyPart.objects.filter(
            display_name=self.display_name, modality=modality
        ).first()

        if existing:
            if existing.deleted:
                existing.deleted = False
                existing.coding = [c.model_dump() for c in self.coding]
                existing.save(update_fields=["deleted", "coding", "modified_date"])
                existing._state.adding = False
                return existing

            raise ValidationError(
                f"Body part '{self.display_name}' already exists for {modality.display_name}."
            )

        obj = BodyPart(
            modality=modality,
            display_name=self.display_name,
            coding=[c.model_dump() for c in self.coding],
        )
        return obj


class BodyPartUpdateSpec(BaseModel):
    modality: Optional[UUID] = None
    display_name: Optional[str] = None
    coding: Optional[List[BodyPartCoding]] = None

    def de_serialize(self, obj: BodyPart, **kwargs) -> BodyPart:
        """Update an existing BodyPart model instance."""
        if self.modality is not None:
            modality = ModalityType.objects.filter(external_id=self.modality).first()
            if not modality:
                raise ValidationError(f"Invalid modality id: {self.modality}")
            obj.modality = modality

        if self.display_name is not None:
            obj.display_name = self.display_name

        if self.coding is not None:
            obj.coding = [c.model_dump() for c in self.coding]

        return obj
