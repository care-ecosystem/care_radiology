import enum

from care.security.permissions.constants import Permission, PermissionContext
from care.security.roles.role import (
    ADMIN_ROLE,
    DOCTOR_ROLE,
    FACILITY_ADMIN_ROLE,
    NURSE_ROLE,
    STAFF_ROLE,
)


class RadiologyPermissions(enum.Enum):
    can_read_radiology_data = Permission(
        "Can Read Radiology Data on Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE, DOCTOR_ROLE, NURSE_ROLE, STAFF_ROLE],
    )
    can_write_radiology_data = Permission(
        "Can Write Radiology Data on Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE],
    )
    can_read_dicom_worklist = Permission(
        "Can Read DICOM Worklist on Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE, DOCTOR_ROLE, NURSE_ROLE, STAFF_ROLE],
    )
    can_write_upload_dicom_study = Permission(
        "Can Upload DICOM Study on Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE],
    )
    can_write_dicom_status = Permission(
        "Can Update DICOM Study and Modality Status on Facility",
        "",
        PermissionContext.FACILITY,
        [FACILITY_ADMIN_ROLE, ADMIN_ROLE],
    )
