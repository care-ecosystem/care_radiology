from pydantic import UUID4

from care.emr.resources.base import EMRResource
from care.emr.resources.diagnostic_report.spec import DiagnosticReportSpecBase
from care.emr.resources.encounter.spec import EncounterSpecBase
from care.emr.resources.service_request.spec import BaseServiceRequestSpec, ServiceRequestRetrieveSpec
from care_radiology.api.specs.dicom import DicomStudyReadSpec, DicomStudyRetrieveSpec
from care_radiology.models.imaging_study import ImagingStudy, ImagingStudyStatus
from care_radiology.services.dicom_service import fetch_studies


class ImagingStudyReadSpec(EMRResource):
    __model__ = ImagingStudy
    __study_spec__ = DicomStudyReadSpec

    id: UUID4 | None = None
    status: ImagingStudyStatus
    accession_number: str | None = None
    encounter: dict
    service_request: dict | None = None
    studies: list[dict] = []

    @classmethod
    def serialize_service_request(cls, service_request):
        data = BaseServiceRequestSpec.serialize(service_request).to_json()
        data["diagnostic_reports"] = [
            DiagnosticReportSpecBase.serialize(report).to_json()
            for report in service_request.diagnosticreport_set.all()[:1]
        ]
        return data

    @classmethod
    def perform_extra_serialization(cls, mapping, obj, *args, pacs_details=None, **kwargs):
        super().perform_extra_serialization(mapping, obj)
        mapping["encounter"] = EncounterSpecBase.serialize(obj.encounter).to_json()
        if obj.service_request:
            mapping["service_request"] = cls.serialize_service_request(obj.service_request)
        studies = obj.studies.all()
        if pacs_details is None:
            pacs_details = fetch_studies(studies)
        mapping["studies"] = [
            cls.__study_spec__.serialize(study, pacs_details=pacs_details[study.id]).to_json()
            for study in studies
            if study.id in pacs_details
        ]


class ImagingStudyRetrieveSpec(ImagingStudyReadSpec):
    __study_spec__ = DicomStudyRetrieveSpec

    @classmethod
    def serialize_service_request(cls, service_request):
        return ServiceRequestRetrieveSpec.serialize(service_request).model_dump(
            mode="json", exclude={"meta", "encounter", "specimens", "tags"}
        )


class ImagingStudyUpdateSpec(EMRResource):
    __model__ = ImagingStudy

    status: ImagingStudyStatus
