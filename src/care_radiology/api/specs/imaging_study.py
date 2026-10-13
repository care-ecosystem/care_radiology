from care.emr.resources.base import EMRResource
from care.emr.resources.diagnostic_report.spec import DiagnosticReportSpecBase
from care.emr.resources.encounter.spec import EncounterSpecBase
from care.emr.resources.service_request.spec import BaseServiceRequestSpec, ServiceRequestRetrieveSpec
from pydantic import UUID4

from care_radiology.api.specs.dicom import DicomStudyReadSpec
from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus
from care_radiology.services.dicom_service import fetch_studies


class ImagingStudyReadSpec(EMRResource):
    __model__ = ImagingStudy

    id: UUID4 | None = None
    status: ImagingStudyStatus
    accession_number: str | None = None
    encounter: dict
    service_request: dict | None = None
    diagnostic_report: dict | None = None
    studies: list[dict] = []

    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        mapping["encounter"] = EncounterSpecBase.serialize(obj.encounter).to_json()
        if obj.service_request:
            mapping["service_request"] = BaseServiceRequestSpec.serialize(obj.service_request).to_json()
            latest_report = max(
                obj.service_request.diagnosticreport_set.all(), key=lambda report: report.created_date, default=None
            )
            if latest_report:
                mapping["diagnostic_report"] = DiagnosticReportSpecBase.serialize(latest_report).to_json()
        mapping["studies"] = [
            DicomStudyReadSpec.serialize(study, pacs_details=details).to_json()
            for study, details in fetch_studies(list(obj.studies.all()))
        ]


class ImagingStudyRetrieveSpec(ImagingStudyReadSpec):
    @classmethod
    def perform_extra_serialization(cls, mapping, obj):
        super().perform_extra_serialization(mapping, obj)
        if obj.service_request:
            mapping["service_request"] = ServiceRequestRetrieveSpec.serialize(obj.service_request).model_dump(
                mode="json", exclude={"meta", "encounter", "specimens", "tags"}
            )


class ImagingStudyUpdateSpec(EMRResource):
    __model__ = ImagingStudy

    status: ImagingStudyStatus
