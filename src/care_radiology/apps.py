import enum
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

from care.security.permissions.base import PermissionController
from care.security.permissions.constants import Permission, PermissionContext
from care.security.roles.role import ADMIN_ROLE, ADMINISTRATOR, DOCTOR_ROLE, FACILITY_ADMIN_ROLE, NURSE_ROLE, PHARMACIST_ROLE, STAFF_ROLE, VOLUNTEER_ROLE

PLUGIN_NAME = "care_radiology"


class RadiologyReportPermissions(enum.Enum):
    can_write_radiology_report = Permission(
        "Can Write Radiology Report at a Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE, NURSE_ROLE],
    )
    can_read_radiology_report = Permission(
        "Can Read Radiology Report",
        "",
        PermissionContext.FACILITY,
        [
            FACILITY_ADMIN_ROLE,
            ADMINISTRATOR,
            ADMIN_ROLE,
            STAFF_ROLE,
            DOCTOR_ROLE,
            NURSE_ROLE,
            VOLUNTEER_ROLE,
            PHARMACIST_ROLE,
        ],
    )

class CareRadiologyPluginConfig(AppConfig):
    name = PLUGIN_NAME
    verbose_name = _("Care radiology plugin")

    def ready(self):
        PermissionController.register_permission_handler(RadiologyReportPermissions)

        from care.security.authorization.base import (AuthorizationHandler, AuthorizationController)
        class RadiologyReportAccess(AuthorizationHandler):
            def can_read_radiology_report(self, user):
                return self.check_permission_in_facility_organization(
                    permissions=[RadiologyReportPermissions.can_read_radiology_report.name],
                    user=user
                )
            def can_write_radiology_report(self, user):
                return self.check_permission_in_facility_organization(
                    permissions=[RadiologyReportPermissions.can_write_radiology_report.name],
                    user=user
                )
        AuthorizationController.register_internal_controller(RadiologyReportAccess)
