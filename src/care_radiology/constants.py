from care_radiology.settings import plugin_settings

DCM4CHEE_BASEURL = plugin_settings.CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL

# The archive's own REST root (without /aets/{AETitle}), which serves the archive-wide operations.
DCM4CHEE_ARCHIVE_BASEURL = DCM4CHEE_BASEURL.split("/aets/", 1)[0]

MPPS_STATUS_SCAN_STARTED = "Scan Started"
MPPS_STATUS_SCAN_COMPLETED = "Scan Completed"
MPPS_STATUS_DISCONTINUED = "Scan Cancelled"

# Facility tag display added to the service request for each imaging study status of the MPPS webhook.
MPPS_TAG_DISPLAY_BY_STATUS = {
    "in_progress": MPPS_STATUS_SCAN_STARTED,
    "completed": MPPS_STATUS_SCAN_COMPLETED,
    "cancelled": MPPS_STATUS_DISCONTINUED,
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

# One key per SOP Instance UID a study has in the PACS, keyed by Study UID, generation and SOP Instance UID.
DICOM_SOP_INSTANCE_KEY_TEMPLATE = "radiology:dicom:study-sops:{}:{}:{}"

# The claim of an upload in progress, keyed by Study UID and SOP Instance UID. It is kept apart from the study's
# generation, so a generation that expires during the upload does not let a second upload of the file through.
DICOM_SOP_INSTANCE_UPLOAD_KEY_TEMPLATE = "radiology:dicom:sop-upload:{}:{}"

# Value an upload claim holds while the files of its failed upload are removed from the PACS, with the token of
# that cleanup. An upload of the same file waits for the claim to be released instead of being rejected as a duplicate.
DICOM_SOP_INSTANCE_CLEANUP_MARKER = "cleanup:{}"

# Expiry of a cleanup marker until its task starts, so a cleanup that never runs does not keep the file from being
# uploaded again. A running cleanup extends it to cover each PACS request before sending it.
DICOM_SOP_INSTANCE_CLEANUP_TIMEOUT = 60

# A cleanup marker this close to expiry is not extended: it could expire, and a new upload claim the file, between
# the check that the marker is the cleanup's own and the extension. Also absorbs the cache round trips.
DICOM_SOP_INSTANCE_CLEANUP_MARGIN = 5

# How long an upload waits for the cleanup of a failed upload of the same file, and how often it checks.
DICOM_SOP_INSTANCE_CLEANUP_WAIT = 10
DICOM_SOP_INSTANCE_CLEANUP_POLL_INTERVAL = 0.2

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
