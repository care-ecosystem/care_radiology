# care_radiology

CARE backend plugin. PRs are reviewed by care_ci; the rules live in
`care-ecosystem/care_reviewer`. Keep this file under 60 lines — it is read on every review run.

## Identity
- `Plug(name=...)`: `care_radiology` — also the API mount, `/api/care_radiology/`
- Django app label (`PLUGIN_NAME`) is the same: `care_radiology`
- Package layout: `src/care_radiology/`

## Entry points
- `apps.py` `ready()` registers, in order: `care_radiology.signals`;
  `RadiologyPermissions` via `PermissionController.register_permission_handler`;
  `care_radiology.security.access`; and two device types with `DeviceTypeRegistry` —
  `DICOM_CARE_TYPE` → `ModalityDevice` and `DICOM_ENABLER_CARE_TYPE` → `ModalityEnablerDevice`.
  It then calls `plugin_settings.validate()`, skipped for `BUILD_TIME_COMMANDS` so CARE images
  can build.
- `urls.py` exports `urlpatterns` from a router. Basenames use the `radiology_<resource>` style
  (`radiology_dicom`, `radiology_imaging_study`), not `<plug>__<resource>`.
- Celery tasks in `tasks/`: `archive_old_studies`, `assign_accession_number`,
  `deactivate_imaging_study`, `move_study_to_patient`.

## Integrates with
- Core models extended via the `extensions` JSONField: none.
- External systems: a DICOM modality worklist / PACS, reached through the
  `care_radiology_dicom_enabler` agent. Device configuration is owned by this plugin, so changes
  under `api/device.py` or `constants.py` can break already-configured facility devices.
- Frontend counterpart: `care_radiology_fe`.

## Deliberate deviations
- Router basenames are `radiology_*` rather than the `care_hello` template's `<plug>__<resource>`.
  This is settled; do not flag it.
