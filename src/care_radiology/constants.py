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

# When a study's last file was uploaded, and whether its PACS patient sync task is queued, so each study has
# one task that moves it once its files stop arriving.
DICOM_STUDY_LAST_UPLOAD_KEY_TEMPLATE = "radiology:dicom:last-upload:{}"
DICOM_STUDY_PATIENT_SYNC_SCHEDULED_KEY_TEMPLATE = "radiology:dicom:patient-sync-scheduled:{}"

# dcm4chee rejection note (code^scheme) applied before a study is deleted from the PACS
PACS_DELETE_REJECTION_CODE = "113001^DCM"

# PACS details kept in a study's meta when it is archived out of the PACS, and read back from
# there when it is serialized. The Study Instance UID is kept too, as `archived_study_uid`, but
# is never read back: an empty study_uid is what marks a study as no longer in the PACS.
ARCHIVED_STUDY_DETAIL_FIELDS = ("study_date", "study_description", "number_of_series", "number_of_instances")
ARCHIVED_STUDY_UID_FIELD = "archived_study_uid"
