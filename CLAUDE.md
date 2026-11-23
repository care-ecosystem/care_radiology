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
- `urls.py` exports `urlpatterns` from a router. Basenames are mixed and that is fine:
  `radiology_dicom`, `radiology_observation_result_template`, `radiology_external`, but the
  imaging-study one is bare `imaging_study`. Neither style is a finding.
- Celery task function names, which differ from their module names: `archive_old_dicom_studies`
  (in `archive_old_studies.py`), `assign_accession_number`, `deactivate_imaging_study`, and
  `move_study_to_care_patient` (in `move_study_to_patient.py`).

## Integrates with
- Core models extended via the `extensions` JSONField: none.
- External systems: a DICOM modality worklist / PACS, reached through the
  `care_radiology_dicom_enabler` agent. Device configuration is owned by this plugin, so changes
  under `api/device.py` or `constants.py` can break already-configured facility devices.
- Frontend counterpart: `care_radiology_fe`.

## Deliberate deviations
- Router basenames do not follow the `care_hello` template's `<plug>__<resource>`, and are not
  even internally consistent. This is settled; do not flag either style.
