from care.security.authorization import AuthorizationController
from care.security.authorization.base import AuthorizationHandler
from care.security.permissions.diagnostic_report import DiagnosticReportPermissions

from care_radiology.security.permissions import RadiologyPermissions


class RadiologyAccess(AuthorizationHandler):
    # Reuses DiagnosticReportPermissions' slug (not a new Permission) under a different action
    # name, since can_read/write_diagnostic_report is already owned by core's ServiceRequestAccess.
    def can_read_radiology_observation_template(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[DiagnosticReportPermissions.can_read_diagnostic_report.name],
            user=user,
            facility=facility,
        )

    def can_write_radiology_observation_template(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[DiagnosticReportPermissions.can_write_diagnostic_report.name],
            user=user,
            facility=facility,
        )

    def can_read_radiology_data(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[RadiologyPermissions.can_read_radiology_data.name],
            user=user,
            facility=facility,
        )

    def can_write_radiology_data(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[RadiologyPermissions.can_write_radiology_data.name],
            user=user,
            facility=facility,
        )


AuthorizationController.register_internal_controller(RadiologyAccess)
