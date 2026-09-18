import sys

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

PLUGIN_NAME = "care_radiology"

# Management commands that run during build time - skip validation for these
BUILD_TIME_COMMANDS = {
    "collectstatic",
    "makemigrations",
    "migrate",
    "compilemessages",
    "check",
    "spectacular",
}


class CareRadiologyPluginConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = _("Care radiology plugin")

    def ready(self):
        import care_radiology.signals  # noqa: F401

        from care.security.permissions.base import PermissionController
        from care_radiology.security.permissions import RadiologyPermissions

        PermissionController.register_permission_handler(RadiologyPermissions)

        import care_radiology.security.access  # noqa: F401

        # Skip validation during build-time commands (allows CARE images to build)
        # Validation happens at runtime when settings are actually needed
        if len(sys.argv) > 1 and sys.argv[1] in BUILD_TIME_COMMANDS:
            return

        from care_radiology.settings import plugin_settings

        plugin_settings.validate()
