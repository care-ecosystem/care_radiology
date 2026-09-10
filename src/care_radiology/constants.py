from django.core.exceptions import ImproperlyConfigured
from care_radiology.settings import plugin_settings


class LazyConfigValue:
    """
    Generic lazy evaluation wrapper for configuration values.
    Validates only when the value is actually used, not at import time.
    This allows CARE images to build without all configuration set.
    """
    def __init__(self, setting_name, error_message):
        self.setting_name = setting_name
        self.error_message = error_message
        self._value = None
        self._validated = False

    def _validate(self):
        if not self._validated:
            value = getattr(plugin_settings, self.setting_name)
            if not value:
                raise ImproperlyConfigured(self.error_message)
            self._value = value
            self._validated = True
        return self._value

    def __str__(self):
        return self._validate()

    def __repr__(self):
        return f"LazyConfigValue({self.setting_name}, {self._value if self._validated else 'not loaded'})"

    def __format__(self, format_spec):
        return format(str(self), format_spec)

    def __eq__(self, other):
        return str(self) == other

    def __hash__(self):
        return hash(str(self))

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)


# Lazy evaluation - values are validated only when used in operations
DCM4CHEE_BASEURL = LazyConfigValue(
    "CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL",
    "CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL is required for PACS operations. "
    "Please set it via environment variable or plugin configuration."
)

WEBHOOK_SECRET = LazyConfigValue(
    "CARE_RADIOLOGY_WEBHOOK_SECRET",
    "CARE_RADIOLOGY_WEBHOOK_SECRET is required for webhook operations. "
    "Please set it via environment variable or plugin configuration."
)

VALID_MPPS_STATUSES = ["SCAN_STARTED", "SCAN_COMPLETED", "DISCONTINUED"]

DICOM_STUDY_CACHE_KEY_TEMPLATE = "radiology:dicom:study:{}"
