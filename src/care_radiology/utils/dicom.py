import logging
from datetime import datetime
from enum import Enum

import requests

from care_radiology.constants import DCM4CHEE_BASEURL
from care_radiology.settings import plugin_settings

logger = logging.getLogger(__name__)


def get_pacs_query_timeout():
    """Returns (connect_timeout, read_timeout) tuple for QIDO-RS queries"""
    return (
        plugin_settings.CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT,
        plugin_settings.CARE_RADIOLOGY_PACS_QUERY_TIMEOUT,
    )


class DICOM_TAG(Enum):
    StudyInstanceUID = "0020000D"
    StudyModalities = "00080061"
    StudyDescription = "00081030"
    StudyDate = "00080020"
    StudyTime = "00080030"
    AccessionNumber = "00080050"

    SeriesInstanceUID = "0020000E"
    SeriesModality = "00080060"
    SeriesNumber = "00200011"
    NumberOfSeriesRelatedInstances = "00201209"
    SeriesDescription = "0008103E"

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

    # Query series list, handle timeout/failure gracefully
    series_data = d_query_series_for_study(study_uid)
    if series_data is None:
        return None

    series = [
        {
            "series_uid": d_find(s, DICOM_TAG.SeriesInstanceUID.value)[0],
            "series_number": d_find(s, DICOM_TAG.SeriesNumber.value),
            "series_instance_count": d_find(s, DICOM_TAG.NumberOfSeriesRelatedInstances.value),
            "series_description": d_find(s, DICOM_TAG.SeriesDescription.value),
            "series_modality": d_find(s, DICOM_TAG.SeriesModality.value),
        }
        for s in series_data
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
        "study_series": series,
    }

    return cachable


def _query_pacs(url, log_ctx, params=None):
    """GET a PACS endpoint and return parsed JSON, or None (logged) on timeout/failure."""
    try:
        response = requests.get(
            url=url,
            headers={"Accept": "application/json"},
            params=params,
            timeout=get_pacs_query_timeout(),
        )
    except requests.Timeout:
        logger.warning("PACS query timeout for %s", log_ctx)
        return None

    if not response.ok:
        logger.warning("PACS query failed for %s: status=%s", log_ctx, response.status_code)
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("PACS returned invalid JSON for %s", log_ctx)
        return None


def d_query_instance(instance_id):
    data = _query_pacs(
        f"{DCM4CHEE_BASEURL}/rs/instances",
        f"instance {instance_id}",
        params={"SOPInstanceUID": instance_id},
    )
    if isinstance(data, list) and data:
        return data[0]

    return None


def d_query_series_for_study(study_id):
    data = _query_pacs(f"{DCM4CHEE_BASEURL}/rs/studies/{study_id}/series", f"study {study_id} series")
    return data or None


def d_query_study(study_uid):
    data = _query_pacs(
        f"{DCM4CHEE_BASEURL}/rs/studies",
        f"study {study_uid}",
        params={
            "StudyInstanceUID": study_uid,
            "includefield": ",".join(
                [
                    DICOM_TAG.StudyDescription.value,
                    DICOM_TAG.StudyModalities.value,
                    DICOM_TAG.StudyDate.value,
                    DICOM_TAG.StudyTime.value,
                ]
            ),
        },
    )
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


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.strptime(date_str, "%Y-%m-%d")


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


# Explicit-VR little endian is mandated for the file meta group, so these are the
# only VRs there that use the 12-byte (reserved + 4-byte length) header form.
_FILE_META_LONG_FORM_VRS = (b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN")

FILE_META_GROUP = 0x0002
MEDIA_STORAGE_SOP_INSTANCE_UID = (0x0002, 0x0003)


def read_sop_instance_uid(file_obj):
    """
    Read MediaStorageSOPInstanceUID (0002,0003) out of a DICOM Part 10 file's meta
    group, which is identical to the dataset's SOPInstanceUID and uniquely identifies
    this one file. Used to detect a re-upload of a file already stored in PACS.

    The meta group is always explicit VR little endian regardless of the transfer
    syntax of the dataset that follows, so it can be parsed without a DICOM library.
    Returns None if the file is not a parseable Part 10 file.
    """
    try:
        file_obj.seek(0)
        if file_obj.read(132)[128:] != b"DICM":
            return None

        while True:
            header = file_obj.read(8)
            if len(header) < 8:
                return None

            group = int.from_bytes(header[0:2], "little")
            element = int.from_bytes(header[2:4], "little")
            vr = header[4:6]

            # Past the meta group the transfer syntax may change, and the UID we want
            # is always present within it, so there is nothing left to look for.
            if group != FILE_META_GROUP:
                return None

            if vr in _FILE_META_LONG_FORM_VRS:
                # Long form: the 2 reserved bytes are header[6:8], already consumed
                # above, and the length is the 4 bytes that follow.
                length = int.from_bytes(file_obj.read(4), "little")
            else:
                length = int.from_bytes(header[6:8], "little")

            value = file_obj.read(length)
            if (group, element) == MEDIA_STORAGE_SOP_INSTANCE_UID:
                # UIDs are padded to an even length with a trailing null byte.
                return value.decode("ascii").rstrip("\x00").strip() or None
    except (OSError, UnicodeDecodeError, ValueError):
        logger.warning("Could not read SOP Instance UID from DICOM file meta group")
        return None
    finally:
        # encode_file_multipart_related() reads the file from the start.
        file_obj.seek(0)
