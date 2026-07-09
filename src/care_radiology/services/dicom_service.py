from django.conf import settings
import requests

from django.core.cache import cache
from django.db.models import OuterRef, Exists

from care.emr.models.service_request import ServiceRequest
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.study_report import StudyReport
from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.utils.dicom import (
    DICOM_TAG,
    d_datetime_to_iso,
    d_find,
    d_query_instance,
    d_query_series_for_study,
    d_query_study,
    encode_file_multipart_related,
)


DCM4CHEE_BASEURL = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL']


class DicomUploadError(Exception):
    def __init__(self, message, status_code=500, extra=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


class WebhookConflictError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def upload_dicom_file(patient, dcm_file):
    if not dcm_file:
        raise DicomUploadError("No file provided", status_code=400)

    try:
        body, content_type = encode_file_multipart_related(dcm_file)
        upload_response = requests.post(
            url=f"{DCM4CHEE_BASEURL}/rs/studies",
            data=body,
            headers={
                "Content-Type": content_type,
                "Accept": "application/dicom+json",
            },
        )

        if upload_response.status_code not in [200, 201]:
            raise DicomUploadError(
                "Failed to upload to DCM4CHE",
                status_code=502,
                extra={"status_code": upload_response.status_code},
            )

        referenced_sop = d_find(
            upload_response.json(), DICOM_TAG.ReferencedSOPSQ.value
        )[0]

        instance_uid = d_find(
            referenced_sop, DICOM_TAG.ReferencedInstanceUID.value
        )[0]

        study_uid = d_find(
            d_query_instance(instance_uid), DICOM_TAG.StudyInstanceUID.value
        )[0]

        studies_qs = DicomStudy.objects.annotate(
            has_report=Exists(
                StudyReport.objects.filter(study=OuterRef('pk'))
            )
        )

        (dicom_study, _) = DicomStudy.objects.update_or_create(
            dicom_study_uid=study_uid,
            patient=patient,
            defaults={},
        )

        dicom_study = studies_qs.get(pk=dicom_study.pk)

        # Bust the study from cache
        key = f"radiology:dicom:study:{study_uid}"
        cache.delete(key)

        return {
            "study_uid": study_uid,
            "study": fetch_study(dicom_study),
        }

    except DicomUploadError:
        raise
    except Exception as e:
        raise DicomUploadError(
            "Exception occurred", status_code=500, extra={"details": str(e)}
        )


def link_service_request_to_study(service_request, study_uid, raw_data=None):
    (study, _) = DicomStudy.objects.get_or_create(
        dicom_study_uid=study_uid, patient=service_request.patient, defaults={}
    )

    (rsr, created) = RadiologyServiceRequest.objects.get_or_create(
        service_request=service_request, dicom_study=study, defaults={"raw_data": raw_data or {}}
    )
    if not created and raw_data is not None:
        rsr.raw_data = raw_data
        rsr.save(update_fields=["raw_data"])

    return {
        "external_id": rsr.external_id,
        "data": rsr.raw_data,
    }


def process_study_webhook(data):
    if data.get("service_request_id") and data.get("study_id"):
        try:
            sr = ServiceRequest.objects.get(external_id=data["service_request_id"])
        except ServiceRequest.DoesNotExist:
            raise WebhookConflictError("No matching service request")

        return link_service_request_to_study(sr, data["study_id"], raw_data=data)

    elif data.get("patient_id") and data.get("study_id"):
        from care.emr.models.patient import Patient

        patient = Patient.objects.filter(
            instance_identifiers__contains=[{"value": data.get("patient_id")}]
        ).first()
        if not patient:
            raise WebhookConflictError("No matching patient")

        (study, _) = DicomStudy.objects.get_or_create(
            dicom_study_uid=data.get("study_id"), patient=patient, defaults={}
        )

        return {
            "external_id": study.external_id,
            "data": data,
        }

    return None


def fetch_study(dicom_study):

    def first(dcm, tag):
        values = d_find(dcm, tag)
        return values[0] if values else None

    study_uid = dicom_study.dicom_study_uid
    key = f"radiology:dicom:study:{study_uid}"
    cached = cache.get(key)
    if cached:
        cached["has_report"] = dicom_study.has_report
        return cached

    study = d_query_study(study_uid)

    if study is None:
        return None

    series = [
        {
            "series_uid": d_find(s, DICOM_TAG.SeriesInstanceUID.value)[0],
            "series_number": d_find(s, DICOM_TAG.SeriesNumber.value),
            "series_instance_count": d_find(
                s, DICOM_TAG.NumberOfSeriesRelatedInstances.value
            ),
            "series_description": d_find(s, DICOM_TAG.SeriesDescription.value),
            "series_modality": d_find(s, DICOM_TAG.SeriesModality.value),
        }
        for s in d_query_series_for_study(study_uid)
    ]

    study_description = (
        d_find(study, DICOM_TAG.StudyDescription.value)[0]
        if len(d_find(study, DICOM_TAG.StudyDescription.value)) > 0
        else None
    )

    study_date_raw = first(study, DICOM_TAG.StudyDate.value)
    study_time_raw = first(study, DICOM_TAG.StudyTime.value)

    if study_date_raw and study_time_raw:
        study_date = d_datetime_to_iso(study_date_raw, study_time_raw)
    elif study_date_raw:
        study_date = d_datetime_to_iso(study_date_raw)
    else:
        study_date = None

    cachable = {
        "study_uid": study_uid,
        "study_date": study_date,
        "study_description": study_description,
        "study_modalities": d_find(study, DICOM_TAG.StudyModalities.value),
        "study_series": series,
        "external_id": dicom_study.external_id,
        "has_report": dicom_study.has_report,
    }

    cache.set(key, cachable, timeout=60 * 60)
    return cachable
