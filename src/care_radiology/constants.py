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

# The active CARE records of a Study UID, so the files of a study being uploaded skip the table lookup.
DICOM_STUDY_LINKS_CACHE_KEY_TEMPLATE = "radiology:dicom:study-links:{}"

# The generation of a study's SOP Instance keys, added once they hold every instance the PACS has. Deleting it
# drops them all at once: later uploads fill a new generation, and the old keys expire.
DICOM_STUDY_SOP_GENERATION_KEY_TEMPLATE = "radiology:dicom:study-sops:{}"

# One key per SOP Instance UID a study has in the PACS or that an upload has claimed, keyed by Study UID,
# generation and SOP Instance UID.
DICOM_SOP_INSTANCE_KEY_TEMPLATE = "radiology:dicom:study-sops:{}:{}:{}"

# Expiry of the study links, refreshed on every upload of the study, and of a study's SOP Instance generation,
# which is not, so an active study's instances are read from the PACS again once it expires.
DICOM_STUDY_UPLOAD_CACHE_TIMEOUT = 60 * 10

# Postgres advisory lock serialising the archive's PACS delete with record creation,
# keyed by Study Instance UID.
DICOM_STUDY_LOCK_KEY_TEMPLATE = "radiology:dicom:study-lock:{}"

# dcm4chee rejection note (code^scheme) applied before a study is deleted from the PACS
PACS_DELETE_REJECTION_CODE = "113001^DCM"

# PACS details kept in a study's meta when it is archived out of the PACS, and read back from
# there when it is serialized. The Study Instance UID is kept too, as `archived_study_uid`, but
# is never read back: an empty study_uid is what marks a study as no longer in the PACS.
ARCHIVED_STUDY_DETAIL_FIELDS = ("study_date", "study_description", "number_of_series", "number_of_instances")
ARCHIVED_STUDY_UID_FIELD = "archived_study_uid"
