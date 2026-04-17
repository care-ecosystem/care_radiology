from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from care_radiology.models.modality_type import ModalityType

class ModalityCoding(BaseModel):
    coding_system: str
    coding_code: str
    coding_display: str

class ModalityTypeListSpec(BaseModel):
    external_id: UUID
    display_name: str
    coding: list[ModalityCoding] | None = None

    @classmethod
    def serialize(cls, obj: ModalityType):
        return cls(
            external_id=obj.external_id,
            display_name=obj.display_name,
            coding=obj.coding or [],
        )

    def to_json(self):
        return self.model_dump()

class ModalityTypeCreateSpec(BaseModel):
    display_name: str
    coding: List[ModalityCoding]

    def de_serialize(self) -> ModalityType:
        """
        Convert validated Pydantic data into a Django ModalityType model instance.
        If a soft-deleted record exists with the same display_name, revive it.
        """
        from rest_framework.exceptions import ValidationError

        # Try to find an existing record
        existing = ModalityType.objects.filter(display_name=self.display_name).first()
        if existing:
            if existing.deleted:
                # Revive soft-deleted record
                existing.deleted = False
                existing.coding = [c.model_dump() for c in self.coding]
                existing.save(update_fields=["deleted", "coding", "modified_date"])
                # Mark this as already saved — prevent INSERT
                existing._state.adding = False
                return existing
            # If not deleted, raise duplicate error
            raise ValidationError(f"Modality type '{self.display_name}' already exists.")

        # Create a brand new instance (normal insert)
        return ModalityType(
            display_name=self.display_name,
            coding=[c.model_dump() for c in self.coding],
        )

class ModalityTypeUpdateSpec(BaseModel):
    display_name: Optional[str] = None
    coding: Optional[List[ModalityCoding]] = None

    def de_serialize(self, obj: ModalityType, **kwargs) -> ModalityType:
        """
        Update an existing ModalityType model instance with provided fields.
        Compatible with EMRModelViewSet.handle_update().
        """
        if self.display_name is not None:
            obj.display_name = self.display_name
        if self.coding is not None:
            obj.coding = [c.model_dump() for c in self.coding]
        return obj
