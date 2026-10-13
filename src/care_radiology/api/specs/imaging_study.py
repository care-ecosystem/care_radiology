from care.emr.resources.activity_definition.spec import BaseActivityDefinitionSpec
from care.emr.resources.base import EMRResource
from care.emr.resources.diagnostic_report.spec import DiagnosticReportSpecBase
from care.emr.resources.encounter.spec import EncounterSpecBase
from care.emr.resources.service_request.spec import BaseServiceRequestSpec
from pydantic import UUID4

from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus


class ImagingStudyReadSpec(EMRResource):
    __model__ = ImagingStudy

    id: UUID4 | None = None
    status: ImagingStudyStatus
    accession_number: str | None = None
    service_request: dict | None = None
    encounter: dict
    activity_definition: dict | None = None
    diagnostic_reports: list[dict] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        mapping["encounter"] = EncounterSpecBase.serialize(obj.encounter).to_json()
        service_request = obj.service_request
        if service_request:
            mapping["service_request"] = BaseServiceRequestSpec.serialize(service_request).to_json()
            if service_request.activity_definition:
                mapping["activity_definition"] = BaseActivityDefinitionSpec.serialize(
                    service_request.activity_definition
                ).to_json()
            mapping["diagnostic_reports"] = [
                DiagnosticReportSpecBase.serialize(report).to_json()
                for report in service_request.diagnosticreport_set.all()
            ]


class ImagingStudyUpdateSpec(EMRResource):
    __model__ = ImagingStudy

    status: ImagingStudyStatus
