from django.db.models import Q

from care.emr.models.organization import FacilityOrganizationUser
from care.security.authorization import AuthorizationController
from care.security.authorization.base import AuthorizationHandler
from care.security.permissions.device import DevicePermissions
from care.security.permissions.diagnostic_report import DiagnosticReportPermissions
from care_radiology.security.permissions import RadiologyPermissions


class RadiologyAccess(AuthorizationHandler):
    # Reuses DiagnosticReportPermissions' slug (not a new Permission) under a different action
    # name, since can_read/write_diagnostic_report is already owned by core's ServiceRequestAccess.
    def can_read_radiology_observation_result_template(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[DiagnosticReportPermissions.can_read_diagnostic_report.name],
            user=user,
            facility=facility,
        )

    def can_write_radiology_observation_result_template(self, user, facility=None):
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

    def can_read_dicom_worklist(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[RadiologyPermissions.can_read_dicom_worklist.name],
            user=user,
            facility=facility,
        )

    def can_write_upload_dicom_study(self, user, facility=None):
        return self.check_permission_in_facility_organization(
            permissions=[RadiologyPermissions.can_write_upload_dicom_study.name],
            user=user,
            facility=facility,
        )

    # With a device, the check is scoped to the device's managing organizations, like core's can_manage_device.
    def can_write_dicom_status(self, user, facility=None, device=None):
        return self.check_permission_in_facility_organization(
            permissions=[RadiologyPermissions.can_write_dicom_status.name],
            user=user,
            orgs=device.facility_organization_cache if device is not None else None,
            facility=facility,
        )

    def get_accessible_radiology_devices(self, qs, user, facility):
        if user.is_superuser:
            return qs
        roles = self.get_role_from_permissions([DevicePermissions.can_list_devices.name])
        organization_ids = list(
            FacilityOrganizationUser.objects.filter(
                user=user, organization__facility=facility, role_id__in=roles
            ).values_list("organization_id", flat=True)
        )
        return qs.filter(
            Q(facility_organization_cache__overlap=organization_ids)
            | Q(current_location__facility_organization_cache__overlap=organization_ids)
        )


AuthorizationController.register_internal_controller(RadiologyAccess)
