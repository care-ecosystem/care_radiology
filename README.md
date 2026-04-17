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
        "DCM4CHEE_DICOMWEB_BASEURL": "http://arc:8080/dcm4chee-arc/aets/DCM4CHEE",
        # Secret used to verify incoming webhooks
        "WEBHOOK_SECRET": "RADOMSECRET"
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
        "DCM4CHEE_DICOMWEB_BASEURL": "http://arc:8080/dcm4chee-arc/aets/DCM4CHEE",
        "WEBHOOK_SECRET": "secure-webhook-secret"
    },
)
plugs = [radiology_plug]
...
```

[Extended Docs on Plug Installation](https://care-be-docs.ohc.network/pluggable-apps/configuration.html)



This plugin was created with [Cookiecutter](https://github.com/audreyr/cookiecutter) using the [ohcnetwork/care-plugin-cookiecutter](https://github.com/ohcnetwork/care-plugin-cookiecutter).
