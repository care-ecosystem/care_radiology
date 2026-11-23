# care_radiology

CARE backend plugin. PRs are reviewed by care_ci; the rules live in
`care-ecosystem/care_reviewer`. Keep this file under 60 lines — it is read on every review run.

## Identity
- `Plug(name=...)`: `care_radiology` — also the API mount, `/api/care_radiology/`
- Django app label (`PLUGIN_NAME`) is the same: `care_radiology`
- Package layout: `src/care_radiology/`

## Entry points
- `apps.py` `ready()` registers, in order: `care_radiology.signals`; `RadiologyPermissions` via
  `PermissionController.register_permission_handler`; `care_radiology.security.access`; and two
  device types with `DeviceTypeRegistry` — `DICOM_CARE_TYPE` → `ModalityDevice` and
  `DICOM_ENABLER_CARE_TYPE` → `ModalityEnablerDevice`. It then calls `plugin_settings.validate()`,
  skipped for `BUILD_TIME_COMMANDS` so CARE images can build.
- `urls.py` exports `urlpatterns` from a router. Basenames: `radiology_dicom`,
  `radiology_observation_result_template`, `radiology_external`, and bare `imaging_study`.
- Celery task function names, which differ from their module names: `archive_old_dicom_studies`
  (in `archive_old_studies.py`), `cleanup_failed_pacs_upload` (in `cleanup_failed_upload.py`),
  `assign_accession_number`, and `deactivate_imaging_study`. `tasks/__init__.py` schedules the
  archive task only when `CARE_RADIOLOGY_STUDY_AUTO_ARCHIVE_ENABLED` is on.

## Integrates with
- Core models extended via the `extensions` JSONField: none.
- External systems: a DICOM modality worklist / PACS, reached through the
  `care_radiology_dicom_enabler` agent. Device configuration is owned by this plugin, so changes
  under `api/device.py` or `constants.py` can break already-configured facility devices. The
  agent-facing surface is `api/viewsets/external.py`: service-account auth, each action calling
  `can_{read,write}_radiology_data` itself rather than going through the EMR mixins.
- Frontend counterpart: `care_radiology_fe`.

## Silent couplings — worth a hard look in review
- `security/authentication.py` picks an endpoint's rate limit from a dict keyed by `url_name`.
  Renaming a route or its `url_name` drops it to the global default limit; nothing errors.
- `/dicom/authenticate/` is the nginx `auth_request` target guarding `/dicomweb/*`: its path and
  200-vs-403 contract are a deployment interface, not an internal endpoint.
- `constants.py` reads `plugin_settings` at import, freezing `DCM4CHEE_BASEURL` and
  `DCM4CHEE_ARCHIVE_BASEURL` out of reach of the `setting_changed` reload. Read new ones at runtime.
- `PLUGIN_CONFIGS` values usually arrive as strings and `PluginSettings._coerce` casts them to the
  default's type, so a new setting whose default has the wrong type silently inverts.
- DICOM upload de-duplication spans `services/dicom_service.py` and the cache key templates in
  `constants.py`: a per-SOP-instance claim, a per-study generation, and cleanup markers for failed
  uploads. Changing a key template, a timeout, or the claim/release order can admit a duplicate or
  wedge a study, and old and new keys coexist across a rolling deploy. Archiving also takes a
  Postgres advisory xact lock keyed by Study UID.

## Deliberate deviations
- Router basenames do not follow the `care_hello` template's `<plug>__<resource>`, and are not even
  internally consistent. This is settled; neither style is a finding.
- `ImagingStudyViewSet.lookup_field` is `service_request__external_id`: the frontend only ever
  holds a service request and needs "its study, or none yet". Studies without one are list-only;
  making them retrievable also means guarding `authorize_{retrieve,update}`, which assume an SR.
- `RadiologyAccess.can_{read,write}_radiology_observation_result_template` check core's
  `DiagnosticReportPermissions` slugs rather than declare new permissions: core owns those slugs.
- `Makefile` and `tests/test_care_hello.py` are untouched cookiecutter boilerplate: the targets do
  not run, there is no test suite or CI test job, and lint is ruff only (line-length 120).
