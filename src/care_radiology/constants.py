from care_radiology.settings import plugin_settings

DCM4CHEE_BASEURL = plugin_settings.CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL

VALID_MPPS_STATUSES = ["SCAN_STARTED", "SCAN_COMPLETED", "DISCONTINUED"]

DICOM_STUDY_CACHE_KEY_TEMPLATE = "radiology:dicom:study:{}"
