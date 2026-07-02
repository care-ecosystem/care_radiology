from django.conf import settings
import requests

from enum import Enum
from datetime import datetime


DCM4CHEE_BASEURL = settings.PLUGIN_CONFIGS['care_radiology']['CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL']

class DICOM_TAG(Enum):
    # Study Tags
    StudyInstanceUID = "0020000D"
    StudyModalities = "00080061"
    StudyDescription = "00081030"
    StudyDate = "00080020"
    StudyTime = "00080030"
    AccessionNumber = "00080050"

    # Series Tags
    SeriesInstanceUID = "0020000E"
    SeriesModality = "00080060"
    SeriesNumber = "00200011"
    NumberOfSeriesRelatedInstances = "00201209"
    SeriesDescription = "0008103E"

    # Instance Tags
    SOPInstanceUID = "00080018"
    ReferencedInstanceUID = "00081155"

    ReferencedSOPSQ = "00081199"

def fetch_study(dicom_study_uid):
    def first(dcm, tag):
        values = d_find(dcm, tag)
        return values[0] if values else None

    study_uid = dicom_study_uid

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
        "study_accession": d_find(study, DICOM_TAG.AccessionNumber.value),
        "study_series": series
    }

    return cachable


def d_query_instance(instance_id):
    response = requests.get(
        url=f"{DCM4CHEE_BASEURL}/rs/instances",
        headers={
            "Accept": "application/json",
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
            "Accept": "application/json",
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
            "Accept": "application/json",
        },
        params={
            "StudyInstanceUID": study_uid,
            "includefield": ",".join([
                DICOM_TAG.StudyDescription.value,
                DICOM_TAG.StudyModalities.value,
                DICOM_TAG.StudyDate.value,
                DICOM_TAG.StudyTime.value,
            ]),
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
