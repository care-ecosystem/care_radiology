from care_radiology.settings import plugin_settings

DCM4CHEE_BASEURL = plugin_settings.CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL

MPPS_STATUS_SCAN_STARTED = "Scan Started"
MPPS_STATUS_SCAN_COMPLETED = "Scan Completed"
MPPS_STATUS_DISCONTINUED = "Scan Cancelled"

# Facility tag display added to the service request for each imaging study status of the MPPS webhook.
MPPS_TAG_DISPLAY_BY_STATUS = {
    "IN_PROGRESS": MPPS_STATUS_SCAN_STARTED,
    "COMPLETED": MPPS_STATUS_SCAN_COMPLETED,
    "CANCELLED": MPPS_STATUS_DISCONTINUED,
}

DICOM_FILE_EXTENSIONS = (".dcm", ".dicom")

# Device care_type of the DICOM devices (one per modality machine) the DICOM Enabler connects to
DICOM_CARE_TYPE = "dicom"

# Device care_type of the DICOM Enabler the DICOM devices of a room connect to
DICOM_ENABLER_CARE_TYPE = "dicom-enabler"

# assignment_status kept in the metadata of a DICOM Enabler or DICOM device; a device without it is unassigned
ASSIGNMENT_STATUS_ASSIGNED = "assigned"
ASSIGNMENT_STATUS_UNASSIGNED = "unassigned"

DICOM_STUDY_CACHE_KEY_TEMPLATE = "radiology:dicom:study:{}"

# Serialises concurrent uploads of the same DICOM file, keyed by SOP Instance UID.
DICOM_UPLOAD_LOCK_KEY_TEMPLATE = "radiology:dicom:upload-lock:{}"

# Postgres advisory lock serialising the archive's PACS delete with record creation,
# keyed by Study Instance UID.
DICOM_STUDY_LOCK_KEY_TEMPLATE = "radiology:dicom:study-lock:{}"

# dcm4chee rejection note (code^scheme) applied before a study is deleted from the PACS
PACS_DELETE_REJECTION_CODE = "113001^DCM"
