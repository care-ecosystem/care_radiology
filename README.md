# Care Radiology Plugin

Django plugin for ohcnetwork/care.

## Upstream

This plugin uses **dcm4che**:
https://github.com/dcm4che/dcm4che

The **dcm4chee-arc-psql** Docker image is sourced from:
https://github.com/dcm4che-dockerfiles/dcm4chee-arc-psql

PostgreSQL database initialization scripts are sourced from:
https://github.com/dcm4che-dockerfiles/postgres-dcm4chee

## Local Development

To develop the plug in local environment along with care, follow the steps below:

1. Go to the care root directory and clone the plugin repository:

```bash
cd care
git clone git@github.com:10bedicu/care_radiology.git
```

2. Add the plugin config in plug_config.py

```python
...

care_radiology_plugin = Plug(
    name="care_radiology",  # Name of the Django app inside the plugin
    package_name="/app/care_radiology",  # Must be /app/<plugin_folder_name>
    version="",  # Keep empty for local development
    configs={
        # Base URL for dcm4che DICOMweb API
        "CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL": "http://arc:8080/dcm4chee-arc/aets/DCM4CHEE",
        # Static API key for the external APIs (worklist, external upload, MPPS status)
        "CARE_RADIOLOGY_WEBHOOK_SECRET": "RADOMSECRET"
    },
)
plugs = [care_radiology_plugin]

...
```

3. Tweak the code in plugs/manager.py, install the plugin in editable mode
```python
...

subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-e", *packages] # add -e flag to install in editable mode
)

...
```

5. Include the `docker-compose.radiology.yaml` in Makefile's up and down targets in `care` and start the containers
    1. Modify the nginx proxy service's exposed port as required by your setup
```makefile
...
TELERADIOLOGY_DOCKER_COMPOSE := ./care_radiology/docker-compose.radiology.yaml
...
up:
	docker compose -f docker-compose.yaml -f $(docker_config_file) -f $(TELERADIOLOGY_DOCKER_COMPOSE) up -d --wait
```

6. Setting Up DCM4CHEE
    1. DCM4CHEE is used as the DICOM archive and requires LDAP + Postgres configuration.
    2. Configure DICOM Storage (MinIO)
        1. Create a bucket named `dicom-bucket` for the dicom images.
        2. Modify the variables in `docker/dcm4che/bucketconfig.ldif` to reflect your setup (if required).
        3. Import the provided LDAP configuration `docker/dcm4che/bucketconfig.ldif` into the LDAP service so DCM4CHEE uses MinIO for object storage.
    3. Configure the Database:
        1. Create a dedicated database in Postgres `CREATE DATABASE dicom`;
        2. Edit the variables in `docker/dcm4che/Makefile` to match your Postgres setup.
        3. Run the target `setup-dicom-db` in `docker/dcm4che/Makefile`

7. Setting up OHIF
    1. OHIF is the web-based DICOM viewer and must point to publicly accessible DICOMweb endpoints.
    2. Update the following keys in `docker/ohif/app-config.js` to point to the publicly accessible URL for dcm4che DICOMweb API
        1. `dataSources[0].wadoRoot`
        2. `dataSources[0].wadoUriRoot`
        3. `dataSources[0].qidoRoot`.
    3. NOTE: These URLs must be reachable from the browser.
    4. Typically in localhost configurations this will look like
```
wadoUriRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/wado',
qidoRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',
wadoRoot: 'https://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',
```


> [!IMPORTANT]
> Do not push these changes in a PR. These changes are only for local development.

## Production Setup

- Clone this repository inside the root directory of the Care backend.
- Add the snippet below to your `plug_config`

```python
...

radiology_plug = Plug(
    name="care_radiology",
    package_name="git+https://github.com/10bedicu/care_radiology.git",
    version="@main",
    configs={
        # can be defined as environment variables in production setup
        "CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL": "http://arc:8080/dcm4chee-arc/aets/DCM4CHEE",
        "CARE_RADIOLOGY_WEBHOOK_SECRET": "secure-webhook-secret",
        # Optional: validation checks, all enabled by default (see Validation Settings below)
        "CARE_RADIOLOGY_REJECT_DUPLICATE_SOP_INSTANCE": False,
        "CARE_RADIOLOGY_VALIDATE_ACCESSION_NUMBER": True,
        "CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR": True,
    },
)
plugs = [radiology_plug]
...
```

### Validation Settings

The plugin validates DICOM uploads and study links before accepting them. Each check is enabled by default and can be disabled in the plugin `configs` or through an environment variable of the same name.

| Setting | Default | What it validates |
| --- | --- | --- |
| `CARE_RADIOLOGY_REJECT_DUPLICATE_SOP_INSTANCE` | `False` | Before uploading, searches the PACS for the file's SOP Instance UID and rejects the upload (`409`) if it is already stored, or if the same file is being uploaded concurrently. The `409` is returned by the plugin; the file is not sent to the PACS. |
| `CARE_RADIOLOGY_VALIDATE_ACCESSION_NUMBER` | `True` | Rejects an upload (`400`) to `patient/{patient_id}/imaging_study/upload/` with a `service_request_id` whose Accession Number (0008,0050) is unreadable, missing, or does not match the service request's imaging study accession number. The external upload always reads the accession number, whatever this setting is, because it links the file by it (see External APIs). |
| `CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR` | `True` | Rejects linking a study (`409`) that is already linked to a different imaging study of the same patient. A study already linked to another patient is rejected whatever this setting is. Applies to both uploads. |

When a check is disabled, a warning is logged for each request that skips it. Disabling a check has these effects:

- `CARE_RADIOLOGY_REJECT_DUPLICATE_SOP_INSTANCE`: the file is sent to the PACS even if it is already stored. dcm4chee silently discards a duplicate SOP Instance UID and still reports success.
- `CARE_RADIOLOGY_VALIDATE_ACCESSION_NUMBER`: a file is accepted for a service request whatever accession number it carries.
- `CARE_RADIOLOGY_UNIQUE_STUDY_PER_SR`: a study already held by another imaging study of the same patient is added to the new one as well, as a second record; the other imaging study keeps its record. A study held by another patient is still rejected.

### Deleting Archived Studies from the PACS

By default, archiving a study (the `patient/{patient_id}/imaging_study/{study_id}/archive/` endpoint or the auto-archive task) also deletes the study's files from dcm4chee, which removes the study from the PACS database too. **This cannot be undone.** Set `CARE_RADIOLOGY_DELETE_STUDY_FROM_PACS_ON_ARCHIVE` to `False` to only hide the study in CARE instead; its files stay in the PACS.

The study's CARE record is kept either way, and is still listed when archived studies are requested, with its archive reason and who archived it. A record whose files were deleted from the PACS has its Study Instance UID cleared - an empty `study_uid` is what marks a study as no longer in the PACS, and the PACS is never queried for it again. Before the files are deleted, the study's `study_date`, `study_description`, `number_of_series` and `number_of_instances` are read from the PACS and kept in the record's `meta`, and they are returned in place of the record's own empty values when it is serialized. The cleared UID is kept there too, as `archived_study_uid`, so the record still says which study was deleted; it is never returned as `study_uid`, since an empty `study_uid` is what marks the study as gone from the PACS. Only `study_modalities` and `study_series` come back empty, along with the viewer link, since the files they describe no longer exist.

| Setting | Default | Description |
| --- | --- | --- |
| `CARE_RADIOLOGY_DELETE_STUDY_FROM_PACS_ON_ARCHIVE` | `True` | When archiving a study, deletes its files from the PACS and clears the Study Instance UID on its CARE record. |

dcm4chee only deletes a study permanently once it is rejected, so the study is first rejected with the rejection note code `113001^DCM`, then deleted. The code is set in `constants.py` (`PACS_DELETE_REJECTION_CODE`) and must be configured as a rejection note in dcm4chee.

The files are deleted before the study is marked archived. If the PACS delete fails, the `patient/{patient_id}/imaging_study/{study_id}/archive/` endpoint returns `502` (or `504` on timeout) and the study stays unarchived. The auto-archive task skips the study and retries it on its next run. A study the PACS no longer has is treated as already deleted. The files are kept in the PACS if another unarchived CARE study record has the same Study Instance UID; the record is then archived with its UID intact, and keeps its PACS details. When the files are deleted, any earlier archived record of the same Study Instance UID has its UID cleared as well, since its files are gone too.

Uploading a study again after it was archived creates a new, active CARE study record under the same imaging study. The archived record is left as it is. If the archive did not delete the files from the PACS, re-uploading the same files is rejected as a duplicate (see `CARE_RADIOLOGY_REJECT_DUPLICATE_SOP_INSTANCE`).

### Patient ID of Uploaded Files

Every upload sends the CARE patient's Patient ID with the file: their UHID, or their external id when they have no UHID. CARE sends it as a query parameter of the STOW-RS request, `POST /rs/studies?PatientID=<id>`. dcm4chee sets each query parameter on the stored file, overwriting the file's own value (its default `updatePolicy=OVERWRITE`). The study is then filed under the CARE patient in the PACS, while the file CARE received is left unchanged.

### External APIs

Machine-to-machine endpoints for the modality worklist server and other integrations live under `facility/{facility_id}/external/`. They authenticate with a CARE service account token (from `users/{username}/generate_service_account_token/`) sent as `Authorization: Token <token>`. A missing or unknown token, or one whose user is not an active, undeleted service account, is a `401`. The service account must also be a member of the facility with the endpoint's permission, or the request is a `403`: `can_read_dicom_worklist` for the worklist, `can_write_upload_dicom_study` for the imaging study upload, and `can_write_dicom_status` for the MPPS status update and the modality status update. The modalities endpoints are scoped by department: a DICOM Enabler or DICOM device is reached through its managing organization (or its current location's organization), so the service account lists and retrieves only the devices it has core's `can_list_devices` on there, and updates the status only of those whose managing organization grants it `can_write_dicom_status`. A device in another department is left out of the list and is a `403` on retrieve and update. Each is rate-limited per source IP by its own setting (django-ratelimit rate strings):

| Endpoint | Purpose | Rate-limit setting (default) |
| --- | --- | --- |
| `GET facility/{facility_id}/external/worklist/` | Active service requests of the facility, newest first, each with its activity definition's locations and the active, available devices at each. Filters: `modality` (a location name: only requests at that location, each listing just that location and its devices), `created_date_after`, `created_date_before`. Paginated with `limit` / `offset` (default 14, max 200) and returns `count`. | `CARE_RADIOLOGY_RATE_LIMIT_DICOM_WORKLIST` (`100/m`) |
| `POST facility/{facility_id}/external/imaging_study/upload/` | Uploads a DICOM file (`file` only) and links it by its Accession Number to the newest non-cancelled imaging study in the facility, whose patient the study then belongs to. A file whose accession number is unreadable, missing, or matches no imaging study is rejected (`400`) before it reaches the PACS. | `CARE_RADIOLOGY_RATE_LIMIT_DICOM_UPLOAD_EXTERNAL` (`2000/m`) |
| `PATCH facility/{facility_id}/external/imaging_study/status/` | MPPS status update: sets the service request's imaging study to `study_status` (`in_progress`, `completed` or `cancelled`; a study already `completed` or `cancelled` keeps its status), then adds the facility tag whose display is the matching MPPS status (`Scan Started`, `Scan Completed` or `Scan Cancelled` respectively) to the service request, if the facility has one. | `CARE_RADIOLOGY_RATE_LIMIT_WEBHOOK_STATUS` (`200/m`) |
| `GET facility/{facility_id}/external/modalities/`<br>`GET .../modalities/{device_id}/`<br>`PATCH .../modalities/{device_id}/status/` | The facility's DICOM Enablers and DICOM devices, for the DICOM Enabler to pick from; one device with its DICOM endpoints; and assigning or unassigning a device. | `CARE_RADIOLOGY_RATE_LIMIT_MODALITIES` (`50/m`) |

### Auto-Archiving Old Studies

A nightly Celery task can archive studies older than a set age. It is **off by default** - nothing is archived automatically unless it is enabled. It archives through the same path as the manual archive endpoint, so `CARE_RADIOLOGY_DELETE_STUDY_FROM_PACS_ON_ARCHIVE` applies to it too: with that setting at its default, auto-archiving **permanently deletes the files from the PACS**.

A study the PACS delete fails for is left unarchived and retried on the next run.

| Setting | Default | Description |
| --- | --- | --- |
| `CARE_RADIOLOGY_STUDY_AUTO_ARCHIVE_ENABLED` | `False` | Enables the nightly task. The schedule is only registered when this is on. |
| `CARE_RADIOLOGY_STUDY_AUTO_ARCHIVE_DAYS` | `365` | Archives studies whose CARE record is older than this many days, by `created_date`. |

### PACS Timeouts

Applied to every request the plugin makes to dcm4chee, in seconds.

| Setting | Default | Description |
| --- | --- | --- |
| `CARE_RADIOLOGY_PACS_CONNECT_TIMEOUT` | `30` | TCP connect timeout for all PACS operations. |
| `CARE_RADIOLOGY_PACS_UPLOAD_TIMEOUT` | `600` | Read timeout for STOW-RS uploads. A large study needs a generous value. |
| `CARE_RADIOLOGY_PACS_QUERY_TIMEOUT` | `60` | Read timeout for QIDO-RS queries and PACS deletes. |

An upload that times out returns `504`, and the file may still have reached the PACS - a cleanup task removes it and releases its upload claim.

### Other Settings

| Setting | Default | Description |
| --- | --- | --- |
| `CARE_RADIOLOGY_RADIOLOGY_CATEGORY` | `imaging` | The service request category treated as radiology. A service request in this category gets an imaging study and an accession number; others are ignored by the plugin. |

[Extended Docs on Plug Installation](https://care-be-docs.ohc.network/pluggable-apps/configuration.html)



This plugin was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) using the [ohcnetwork/care-plugin-cookiecutter](https://github.com/ohcnetwork/care-plugin-cookiecutter).
