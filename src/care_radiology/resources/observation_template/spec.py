from pydantic import UUID4, BaseModel, field_validator

from care.emr.models.activity_definition import ActivityDefinition
from care.emr.resources.activity_definition.spec import BaseActivityDefinitionSpec
from care.emr.resources.base import EMRResource
from care.emr.resources.facility.spec import FacilityBareMinimumSpec
from care.emr.models.observation_definition import ObservationDefinition
from care.emr.resources.observation_definition.spec import BaseObservationDefinitionSpec
from care.facility.models import Facility

from care_radiology.models.observation_template import (
    ObservationTemplate,
    ObservationTemplateData,
)


class ObservationTemplateFieldSpec(BaseModel):
    code: str
    value: str
    description: str | None = None


class BaseObservationTemplateSpec(EMRResource):
    __model__ = ObservationTemplate
    __exclude__ = ["facility", "observation_definition", "activity_definition"]

    id: UUID4 | None = None
    title: str
    description: str | None = None
    fields: list[ObservationTemplateFieldSpec]


class ObservationTemplateCreateSpec(BaseObservationTemplateSpec):
    facility: UUID4
    observation_definition: UUID4
    activity_definition: UUID4 | None = None

    @field_validator("facility")
    @classmethod
    def validate_facility_exists(cls, facility):
        if not Facility.objects.filter(external_id=facility).exists():
            raise ValueError("Facility not found")
        return facility

    @field_validator("observation_definition")
    @classmethod
    def validate_observation_definition_exists(cls, observation_definition):
        if not ObservationDefinition.objects.filter(
            external_id=observation_definition
        ).exists():
            raise ValueError("Observation definition not found")
        return observation_definition

    @field_validator("activity_definition")
    @classmethod
    def validate_activity_definition_exists(cls, activity_definition):
        if activity_definition and not ActivityDefinition.objects.filter(
            external_id=activity_definition
        ).exists():
            raise ValueError("Activity definition not found")
        return activity_definition

    @field_validator("fields")
    @classmethod
    def validate_fields_not_empty(cls, fields):
        if not fields:
            raise ValueError("At least one field (code/value) is required")
        return fields

    def perform_extra_deserialization(self, is_update, obj):
        obj.facility = Facility.objects.get(external_id=self.facility)
        obj.observation_definition = ObservationDefinition.objects.get(
            external_id=self.observation_definition
        )
        obj.activity_definition = (
            ActivityDefinition.objects.get(external_id=self.activity_definition)
            if self.activity_definition
            else None
        )
        obj.save()
        obj.data.all().delete()
        ObservationTemplateData.objects.bulk_create(
            [
                ObservationTemplateData(
                    template=obj,
                    code=field.code,
                    value=field.value,
                    description=field.description,
                )
                for field in self.fields
            ]
        )


class ObservationTemplateUpdateSpec(EMRResource):
    __model__ = ObservationTemplate
    title: str | None = None
    description: str | None = None


class ObservationTemplateReadSpec(BaseObservationTemplateSpec):
    facility: dict | None = None
    observation_definition: dict | None = None
    activity_definition: dict | None = None
    fields: list[ObservationTemplateFieldSpec] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        mapping["id"] = obj.external_id
        mapping["facility"] = FacilityBareMinimumSpec.serialize(obj.facility).to_json()
        mapping["observation_definition"] = BaseObservationDefinitionSpec.serialize(
            obj.observation_definition
        ).to_json()
        mapping["activity_definition"] = (
            BaseActivityDefinitionSpec.serialize(obj.activity_definition).to_json()
            if obj.activity_definition
            else None
        )
        mapping["fields"] = [
            {"code": data.code, "value": data.value, "description": data.description}
            for data in obj.data.all()
        ]
