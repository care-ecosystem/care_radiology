import io
import logging
import zlib
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
    """Encode a DICOM file as a multipart/related request body."""
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


# Every VR that uses the 12-byte (VR, reserved, 4-byte length) header in explicit VR.
_EXPLICIT_VR_LONG_FORM_VRS = (b"OB", b"OD", b"OF", b"OL", b"OV", b"OW", b"SQ", b"SV", b"UC", b"UN", b"UR", b"UT", b"UV")

TRANSFER_SYNTAX_UID = (0x0002, 0x0010)
ACCESSION_NUMBER = (0x0008, 0x0050)

IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"
EXPLICIT_VR_BIG_ENDIAN = "1.2.840.10008.1.2.2"
DEFLATED_EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1.99"

UNDEFINED_LENGTH = 0xFFFFFFFF

_INFLATE_CHUNK_SIZE = 64 * 1024

_MAX_VALUE_LENGTH = 1024


class DicomParseError(Exception):
    """The file could not be parsed far enough to tell whether it holds a value."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class _InflatingReader:
    """
    Read-only stream over a raw-deflated dataset that inflates only as much as is read.

    The parser stops at the first tag past the Accession Number, so this avoids
    decompressing the whole file without imposing a fixed cut-off that would make
    a valid dataset look truncated.
    """

    def __init__(self, raw):
        self._raw = raw
        self._inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        self._buffer = bytearray()

    def read(self, length):
        while len(self._buffer) < length and not self._inflater.eof:
            # Feed back what the previous call left unconsumed before reading more
            # input, and cap each call's output so a small input cannot expand
            # unboundedly in a single step.
            data = self._inflater.unconsumed_tail or self._raw.read(_INFLATE_CHUNK_SIZE)
            if not data:
                break
            self._buffer += self._inflater.decompress(data, _INFLATE_CHUNK_SIZE)
        chunk = bytes(self._buffer[:length])
        del self._buffer[:length]
        return chunk


def _read_exact(stream, length):
    data = stream.read(length)
    if len(data) < length:
        raise DicomParseError("File ends in the middle of a data element")
    return data


def _read_element_header(stream, implicit_vr, byteorder):
    """
    Read one data element's header, returning (tag, value length), or None at a clean
    end of data. The value is left unread so the caller can decide from the tag
    whether it is worth reading at all.
    """
    header = stream.read(4)
    if not header:
        return None
    if len(header) < 4:
        raise DicomParseError("File ends in the middle of a data element")
    tag = (int.from_bytes(header[0:2], byteorder), int.from_bytes(header[2:4], byteorder))

    if implicit_vr:
        length = int.from_bytes(_read_exact(stream, 4), byteorder)
    else:
        vr = _read_exact(stream, 2)
        if vr in _EXPLICIT_VR_LONG_FORM_VRS:
            _read_exact(stream, 2)
            length = int.from_bytes(_read_exact(stream, 4), byteorder)
        else:
            length = int.from_bytes(_read_exact(stream, 2), byteorder)
    return tag, length


def _check_defined_length(tag, length):
    if length == UNDEFINED_LENGTH:
        raise DicomParseError(
            f"Undefined-length element ({tag[0]:04X},{tag[1]:04X}) before the accession number is not supported"
        )


def _read_value(stream, tag, length):
    """Read a value the parser needs, refusing lengths no valid value of that tag has."""
    _check_defined_length(tag, length)
    if length > _MAX_VALUE_LENGTH:
        raise DicomParseError(f"Element ({tag[0]:04X},{tag[1]:04X}) declares an implausible length of {length} bytes")
    return _read_exact(stream, length)


def _skip_value(stream, tag, length):
    """Move past a value without holding it in memory."""
    _check_defined_length(tag, length)
    if hasattr(stream, "seek"):
        # Seeking past the end would not fail, so check the declared length fits.
        position = stream.tell()
        end = stream.seek(0, io.SEEK_END)
        if position + length > end:
            raise DicomParseError("File ends in the middle of a data element")
        stream.seek(position + length)
        return
    while length:
        length -= len(_read_exact(stream, min(length, _INFLATE_CHUNK_SIZE)))


def read_accession_number(file_obj):
    """
    Read Accession Number (0008,0050) from a DICOM Part 10 file.
    Returns None if missing or empty; raises DicomParseError if the file
    cannot be parsed far enough to determine the value.
    """
    try:
        file_obj.seek(0)
        if file_obj.read(132)[128:] != b"DICM":
            raise DicomParseError("Not a DICOM Part 10 file (missing DICM preamble)")

        transfer_syntax = None
        while True:
            # Only the group is peeked at before reading on: past the meta group the
            # dataset may use another encoding, so its element must not be parsed here.
            dataset_start = file_obj.tell()
            group = file_obj.read(2)
            if len(group) < 2:
                raise DicomParseError("File contains no dataset after the file meta group")
            file_obj.seek(dataset_start)
            if int.from_bytes(group, "little") != FILE_META_GROUP:
                break
            tag, length = _read_element_header(file_obj, implicit_vr=False, byteorder="little")
            if tag == TRANSFER_SYNTAX_UID:
                value = _read_value(file_obj, tag, length)
                transfer_syntax = value.decode("ascii").rstrip("\x00").strip()
            else:
                _skip_value(file_obj, tag, length)

        stream = file_obj
        if transfer_syntax == DEFLATED_EXPLICIT_VR_LITTLE_ENDIAN:
            stream = _InflatingReader(file_obj)

        implicit_vr = transfer_syntax == IMPLICIT_VR_LITTLE_ENDIAN
        byteorder = "big" if transfer_syntax == EXPLICIT_VR_BIG_ENDIAN else "little"

        while True:
            header = _read_element_header(stream, implicit_vr, byteorder)
            if header is None:
                return None
            tag, length = header
            # Elements are in ascending tag order, so once past the accession number
            # it is known to be absent, whatever this element's value holds.
            if tag > ACCESSION_NUMBER:
                return None
            if tag == ACCESSION_NUMBER:
                value = _read_value(stream, tag, length)
                # SH values are padded to an even length with a trailing space.
                return value.decode("ascii", errors="replace").rstrip("\x00").strip() or None
            _skip_value(stream, tag, length)
    except DicomParseError as e:
        logger.warning("Could not read Accession Number from DICOM file: %s", e.message)
        raise
    except (OSError, UnicodeDecodeError, ValueError, zlib.error) as e:
        logger.warning("Could not read Accession Number from DICOM file: %s", e)
        raise DicomParseError(f"Could not parse DICOM file: {e}") from e
    finally:
        # encode_file_multipart_related() reads the file from the start.
        file_obj.seek(0)
