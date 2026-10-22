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

DICOM_STUDY_CACHE_KEY_TEMPLATE = "radiology:dicom:study:{}"

# Serialises concurrent uploads of the same DICOM file, keyed by SOP Instance UID.
DICOM_UPLOAD_LOCK_KEY_TEMPLATE = "radiology:dicom:upload-lock:{}"

# Postgres advisory lock serialising the archive's PACS delete with record creation,
# keyed by Study Instance UID.
DICOM_STUDY_LOCK_KEY_TEMPLATE = "radiology:dicom:study-lock:{}"

# dcm4chee rejection note (code^scheme) applied before a study is deleted from the PACS
PACS_DELETE_REJECTION_CODE = "113001^DCM"
