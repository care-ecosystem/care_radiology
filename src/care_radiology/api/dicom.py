from django.conf import settings
import requests

from enum import Enum
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.cache import cache
from django.db.models import Q, OuterRef, Exists
from django.contrib.auth.models import AnonymousUser

from care.emr.models.device import Device
from care.security.authorization.base import AuthorizationController
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from care.emr.models.patient import Patient
from care.emr.models.service_request import ServiceRequest
from care_radiology.models.radiology_service_request import RadiologyServiceRequest
from care_radiology.models.dicom_study import DicomStudy
from care_radiology.models.study_report import StudyReport


DCM4CHEE_BASEURL = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL']
STATIC_API_KEY = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_WEBHOOK_SECRET']
ACCEPT_JSON = "application/json"

class StaticAPIKeyAuthentication(BaseAuthentication, BasePermission):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")

    def has_permission(self, request):
        api_key = request.headers.get("Authorization")
        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)
        raise AuthenticationFailed("Invalid API key")



class DICOM_TAG(Enum):
    # Study Tags
    StudyInstanceUID = "0020000D"
    StudyModalities = "00080061"
    StudyDescription = "00081030"
    StudyDate = "00080020"
    StudyTime = "00080030"

    # Series Tags
    SeriesInstanceUID = "0020000E"
    SeriesModality = "00080060"
    SeriesNumber = "00200011"
    NumberOfSeriesRelatedInstances = "00201209"
    SeriesDescription = "0008103E"

    # Instance Tags
    SOPInstanceUID = "00080018"
    ReferencedInstanceUID = "00081155"

    # SOP Sequence Tags
    ReferencedSOPSQ = "00081199"  # For successful uploads
    FailedSOPSQ = "00081198"      # For duplicate/conflict (409) responses


class DicomViewSet(ViewSet):

    # A dummy API for JWT verification called by nginx-proxy for dicomweb requests
    @action(detail=False, methods=["get"], url_path="authenticate")
    def authenticate(self, _):
        return Response(status=200)

    @action(
        detail=False,
        methods=["get"],
        url_path="worklist",
        permission_classes = [AllowAny]
    )
    def worklist(self, request):
        # Manually authenticate
        authenticator = StaticAPIKeyAuthentication()
        user_auth_tuple = authenticator.authenticate(request)
        if user_auth_tuple is None:
            raise AuthenticationFailed("Invalid API key")

        modality = request.query_params.get("modality", None)
        from_date = parse_date(request.query_params.get("from"))
        to_date = parse_date(request.query_params.get("to"))
        facility = request.query_params.get("facility")

        results = get_service_requests(
            modality=modality,
            from_date=from_date,
            to_date=to_date,
            limit=1000,  # optional, default is 1000
        )

        return Response(data={
            "status": "success",
            "results": results
        }, status=200)

    # DCM Files upload
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        patient = Patient.objects.get(external_id=request.data.get("patient_id"))
        dcm_file = request.FILES.get("file")

        if not AuthorizationController.call("can_write_patient_obj", self.request.user, patient):
            raise PermissionDenied("You do not have permission to upload DICOM for this patient")

        if not dcm_file:
            return Response({"error": "No file provided"}, status=400)

        try:
            body, content_type = encode_file_multipart_related(dcm_file)

            print("Content Type:", content_type)
            print("DCM4CHEE_BASEURL:", DCM4CHEE_BASEURL)

            upload_response = requests.post(
                url=f"{DCM4CHEE_BASEURL}/rs/studies",
                data=body,
                headers={
                    "Content-Type": content_type,
                    "Accept": "application/dicom+json",
                },
            )

            print("STATUS:", upload_response.status_code)
            print("RAW TEXT:", upload_response.text)

            # ✅ Accept 409 as success
            if upload_response.status_code in [200, 201, 202, 409]:

                data = upload_response.json()

                try:
                    # Try ReferencedSOPSQ first (for successful uploads)
                    ref_sop_list = d_find(data, DICOM_TAG.ReferencedSOPSQ.value)

                    # If not found, try FailedSOPSQ (for 409 conflicts/duplicates)
                    if not ref_sop_list:
                        ref_sop_list = d_find(data, DICOM_TAG.FailedSOPSQ.value)

                    if not ref_sop_list:
                        raise ValueError("No SOP sequence found in response")

                    ref_sop = ref_sop_list[0]

                    instance_uid_list = d_find(
                        ref_sop, DICOM_TAG.ReferencedInstanceUID.value
                    )

                    if not instance_uid_list:
                        raise ValueError("No instance UID found in SOP sequence")

                    instance_uid = instance_uid_list[0]

                    # Get study UID from DCM4CHEE query
                    instance_data = d_query_instance(instance_uid)
                    if instance_data:
                        study_uid_list = d_find(instance_data, DICOM_TAG.StudyInstanceUID.value)
                        if study_uid_list:
                            study_uid = study_uid_list[0]
                        else:
                            raise ValueError("No study UID found in instance data")
                    else:
                        raise ValueError(f"Instance {instance_uid} not found in DCM4CHEE")

                except Exception as parse_error:
                    print(f"DICOM parse error: {parse_error}")
                    study_uid = None

                # ✅ Store mapping only if available
                if study_uid:
                    DicomStudy.objects.update_or_create(
                        dicom_study_uid=study_uid,
                        patient=patient,
                        defaults={},
                    )

                    # Bust cache
                    cache.delete(f"radiology:dicom:study:{study_uid}")

                return Response(
                    data={
                        "status": "success",
                        "message": (
                            "DICOM already exists in DCM4CHEE"
                            if upload_response.status_code == 409
                            else "DICOM uploaded successfully"
                        ),
                        "study_uid": study_uid,
                        "dicom_response": data,
                        # "study": fetch_study(dicom_study),
                    },
                    status=200,
                )

            # ❌ Real failure
            else:
                return Response(
                    data={
                        "error": "Failed to upload to DCM4CHEE",
                        "status_code": upload_response.status_code,
                        "details": upload_response.text,
                    },
                    status=502,
                )

        except Exception as e:
            print("UPLOAD ERROR:", str(e))
            return Response(
                data={"error": "Exception occurred", "details": str(e)},
                status=500,
            )

    # Get list of studies
    @action(detail=False, methods=["get"], url_path="studies")
    def get_studies(self, request):
        patient_external_id = request.query_params.get("patientId")

        patient = Patient.objects.get(external_id=patient_external_id)
        if not AuthorizationController.call("can_view_patient_obj", self.request.user, patient):
            raise PermissionDenied("You do not have permission to view this patient")

        report_exists = StudyReport.objects.filter(study=OuterRef('pk'))
        studies = DicomStudy.objects.filter(patient__external_id=patient_external_id).annotate(has_report=Exists(report_exists))

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {
                executor.submit(fetch_study, study): study
                for study in studies
            }
            for future in as_completed(future_to_study):
                result = future.result()
                if result is not None:
                    results.append(result)

        return Response(results, status=200)

    @action(
        detail=False,
        methods=["get"],
        url_path="service-requests",
        authentication_classes=[],
        permission_classes=[AllowAny],
    )
    def get_servicerequests(self, request):
        service_request_external_id = request.query_params.get("serviceRequestId")

        service_request = ServiceRequest.objects.get(external_id=service_request_external_id)
        if not AuthorizationController.call("can_write_service_request", self.request.user, service_request):
            raise PermissionDenied("You do not have permission to view this service request")

        report_exists = StudyReport.objects.filter(study=OuterRef("dicom_study__pk"))
        tsr = RadiologyServiceRequest.objects.filter(
            service_request__external_id=service_request_external_id,
            dicom_study__dicom_study_uid__isnull=False,
        ).annotate(has_report=Exists(report_exists)).select_related("dicom_study")

        for r in tsr:
            r.dicom_study.has_report = r.has_report


        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_study = {
                executor.submit(fetch_study, r.dicom_study): r
                for r in tsr
            }

            for future in as_completed(future_to_study):
                results.append(future.result())

        return Response(
            results,
            status=200,
        )


def fetch_study(dicom_study: DicomStudy):
    study_uid = dicom_study.dicom_study_uid
    key = f"radiology:dicom:study:{study_uid}"
    cached = cache.get(key)
    if cached:
        cached["has_report"] = dicom_study.has_report
        return cached

    study = d_query_study(study_uid)

    if study is None:
        return None

    series = []
    for s in d_query_series_for_study(study_uid):
        series_uid_list = d_find(s, DICOM_TAG.SeriesInstanceUID.value)
        if not series_uid_list:
            continue  # Skip series without a valid UID

        series.append({
            "series_uid": series_uid_list[0],
            "series_number": d_find(s, DICOM_TAG.SeriesNumber.value),
            "series_instance_count": d_find(
                s, DICOM_TAG.NumberOfSeriesRelatedInstances.value
            ),
            "series_description": d_find(s, DICOM_TAG.SeriesDescription.value),
            "series_modality": d_find(s, DICOM_TAG.SeriesModality.value),
        })

    study_description = (
        d_find(study, DICOM_TAG.StudyDescription.value)[0]
        if len(d_find(study, DICOM_TAG.StudyDescription.value)) > 0
        else None
    )

    study_date_raw = d_find(study, DICOM_TAG.StudyDate.value)
    study_time_raw = d_find(study, DICOM_TAG.StudyTime.value)

    study_date = d_datetime_to_iso(
        study_date_raw[0] if study_date_raw else None,
        study_time_raw[0] if study_time_raw else None,
    )

    cachable = {
        "study_uid": study_uid,
        "study_date": study_date,
        "study_description": study_description,
        "study_modalities": d_find(study, DICOM_TAG.StudyModalities.value),
        "study_series": series,
        "external_id": dicom_study.external_id,
        "has_report": dicom_study.has_report
    }

    cache.set(key, cachable, timeout=60 * 60)
    return cachable

def get_service_requests(
    *,
    from_date=None,
    to_date=None,
    modality=None,
    limit=1000,
):
    filters = Q(status="active", deleted=False)

    if modality:
        device_location_ids = Device.objects.filter(
            registered_name__iexact=modality
        ).values_list("current_location_id", flat=True)
        filters &= Q(activity_definition__locations__overlap=device_location_ids)

    if from_date:
        filters &= Q(created_date__gte=from_date)

    if to_date:
        filters &= Q(created_date__lte=to_date)

    qs = ServiceRequest.objects.filter(filters).select_related(
        "patient", "facility", "activity_definition"
    )[:limit]

    results = []
    for sr in qs:
        results.append(
            {
                "service_request": {
                    "id": sr.external_id,
                    "name": sr.activity_definition.title,
                    "date": sr.created_date
                },
                "facility": {
                    "id": sr.facility.external_id,
                    "name": sr.facility.name
                },
                "patient": {
                    "name": sr.patient.name,
                    "address": sr.patient.address,
                    "phone_number": sr.patient.phone_number,
                    "gender": sr.patient.gender,
                    "age": sr.patient.age
                }
            }
        )

    return results

# Dicom Web Utilities ---------------------------------------------------------
def d_query_instance(instance_id):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/instances",
        headers={
            "Accept": ACCEPT_JSON,
        },
        params={"SOPInstanceUID": instance_id},
    )

    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if isinstance(data, list) and data:
        return data[0]

    return None


def d_query_series_for_study(study_id):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/studies/{study_id}/series",
        headers={
            "Accept": ACCEPT_JSON,
        },
    )

    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if data:
        return data
    else:
        return None


def d_query_study(study_uid):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/studies",
        headers={
            "Accept": ACCEPT_JSON,
        },
        params={
            "StudyInstanceUID": study_uid,
            "includefield": f"{DICOM_TAG.StudyDescription.value},{DICOM_TAG.StudyModalities.value}",
        },
    )

    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    if isinstance(data, list) and data:
        return data[0]

    return None


def d_find(data: any, key):
    results = []
    if isinstance(data, dict):
        if key in data:
            results.extend(data[key].get("Value", []))
        for v in data.values():
            results.extend(d_find(v, key))
    elif isinstance(data, list):
        for item in data:
            results.extend(d_find(item, key))

    return results


def d_datetime_to_iso(da, tm=None):
    if not da:
        return None

    # Parse date
    year = int(da[0:4])
    month = int(da[4:6])
    day = int(da[6:8])

    if tm:
        # Parse time (HHMMSS[.ffffff])
        hours = int(tm[0:2])
        minutes = int(tm[2:4])
        seconds = int(tm[4:6])
        microseconds = 0

        if "." in tm:
            fraction = tm.split(".")[1]
            fraction = (fraction + "000000")[:6]
            microseconds = int(fraction)

        dt = datetime(year, month, day, hours, minutes, seconds, microseconds)
    else:
        dt = datetime(year, month, day)

    return dt.isoformat()

# Date utils ------------------------------------------------------------------
def parse_date(date_str):
    if not date_str:
        return None
    try:
        # Try full datetime first
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback to date-only if time not provided
        return datetime.strptime(date_str, "%Y-%m-%d")

# Multipart Related Encoder ---------------------------------------------------
def encode_file_multipart_related(file_obj):
    import uuid

    boundary = f"DICOMBOUNDARY-{uuid.uuid4().hex}"
    file_bytes = file_obj.read()

    body = (
        (
            f"--{boundary}\r\n"
            f"Content-Type: application/dicom\r\n"
            f"Content-Length: {len(file_bytes)}\r\n"
            f"\r\n"
        ).encode("utf-8")
        + file_bytes
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    content_type = f'multipart/related; type="application/dicom"; boundary={boundary}'

    return body, content_type
