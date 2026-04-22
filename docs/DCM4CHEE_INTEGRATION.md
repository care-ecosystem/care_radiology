# DCM4CHEE Archive - Technical Integration Documentation

## Overview

**DCM4CHEE Archive** is an enterprise-class PACS (Picture Archiving and Communication System) implementation that provides comprehensive DICOM storage, query, and retrieval capabilities.

**Version**: 5.34.1
**Image**: `dcm4che/dcm4chee-arc-psql:5.34.1`
**Project**: https://github.com/dcm4che/dcm4chee-arc-light

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  DCM4CHEE Archive Container                                               │
│  ───────────────────────────────────────────────────────────────────     │
│                                                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  WildFly Application Server (Port 8080)                            │  │
│  │  ────────────────────────────────────────────────────────────────  │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────────────────────────────────────────┐ │  │
│  │  │  dcm4chee-arc-ear (Enterprise Application)                   │ │  │
│  │  │  ──────────────────────────────────────────────────────────  │ │  │
│  │  │                                                              │ │  │
│  │  │  Web Services:                                               │ │  │
│  │  │  ┌────────────────────────────────────────────────────────┐ │ │  │
│  │  │  │  DICOMweb Services                                      │ │ │  │
│  │  │  │  ─────────────────────────────────────────────────────  │ │ │  │
│  │  │  │  - STOW-RS:  POST   /rs/studies                        │ │ │  │
│  │  │  │  - QIDO-RS:  GET    /rs/studies                        │ │ │  │
│  │  │  │  - QIDO-RS:  GET    /rs/series                         │ │ │  │
│  │  │  │  - QIDO-RS:  GET    /rs/instances                      │ │ │  │
│  │  │  │  - WADO-RS:  GET    /rs/studies/{uid}/...              │ │ │  │
│  │  │  │  - WADO-URI: GET    /wado                              │ │ │  │
│  │  │  └────────────────────────────────────────────────────────┘ │ │  │
│  │  │                                                              │ │  │
│  │  │  ┌────────────────────────────────────────────────────────┐ │ │  │
│  │  │  │  Management UI                                          │ │ │  │
│  │  │  │  ─────────────────────────────────────────────────────  │ │ │  │
│  │  │  │  - Web Interface: /dcm4chee-arc/ui2                    │ │ │  │
│  │  │  │  - Study Browser, Configuration, Monitoring            │ │ │  │
│  │  │  └────────────────────────────────────────────────────────┘ │ │  │
│  │  │                                                              │ │  │
│  │  │  ┌────────────────────────────────────────────────────────┐ │ │  │
│  │  │  │  DICOM Services (Port 11112)                           │ │ │  │
│  │  │  │  ─────────────────────────────────────────────────────  │ │ │  │
│  │  │  │  - C-STORE (receive DICOM from modalities)             │ │ │  │
│  │  │  │  - C-FIND (query)                                      │ │ │  │
│  │  │  │  - C-MOVE (retrieve)                                   │ │ │  │
│  │  │  │  - C-ECHO (connectivity test)                          │ │ │  │
│  │  │  └────────────────────────────────────────────────────────┘ │ │  │
│  │  │                                                              │ │  │
│  │  │  ┌────────────────────────────────────────────────────────┐ │ │  │
│  │  │  │  Storage Management                                     │ │ │  │
│  │  │  │  ─────────────────────────────────────────────────────  │ │ │  │
│  │  │  │  - Storage Provider Interface                          │ │ │  │
│  │  │  │  - Cloud Storage Support (S3, Azure, GCS)              │ │ │  │
│  │  │  │  - Multi-tier storage (ONLINE/NEARLINE/ARCHIVE)        │ │ │  │
│  │  │  └────────────────────────────────────────────────────────┘ │ │  │
│  │  └──────────────────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌──────────────────────────┐  ┌───────────────────────────────────────┐ │
│  │  LDAP Client             │  │  PostgreSQL JDBC Driver                │ │
│  │  (Reads configuration)   │  │  (Metadata storage)                    │ │
│  └────────┬─────────────────┘  └─────────┬─────────────────────────────┘ │
│           │                               │                               │
└───────────┼───────────────────────────────┼───────────────────────────────┘
            │                               │
            │                               │
     ┌──────▼─────────┐            ┌───────▼────────────┐
     │  OpenLDAP      │            │  PostgreSQL        │
     │  (Port 389)    │            │  (Port 5432)       │
     │                │            │                    │
     │  - Device      │            │  Tables:           │
     │    Config      │            │  - study           │
     │  - Storage     │            │  - series          │
     │    Descriptors │            │  - instance        │
     │  - AE Titles   │            │  - patient         │
     │  - Network     │            │  - code            │
     │    Config      │            │  - metadata        │
     └────────────────┘            │  - queue           │
                                   └───────┬────────────┘
                                           │
                                    ┌──────▼────────┐
                                    │  MinIO (S3)   │
                                    │  (Port 9000)  │
                                    │               │
                                    │  Bucket:      │
                                    │  dicom-bucket │
                                    │               │
                                    │  Objects:     │
                                    │  {study_uid}/ │
                                    │    {series}/  │
                                    │      {inst}.dcm│
                                    └───────────────┘
```

---

## Docker Configuration

### Container Specification

**docker-compose.radiology.yaml**:
```yaml
arc:
  image: dcm4che/dcm4chee-arc-psql:5.34.1
  environment:
    POSTGRES_DB: dicom
    POSTGRES_HOST: host.docker.internal
    POSTGRES_PORT: 5432
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
    WILDFLY_WAIT_FOR: ldap:389
  depends_on:
    - ldap
  ports:
    - "8080:8080"
    - "11112:11112"  # DICOM protocol (optional, for modalities)
```

### Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `POSTGRES_DB` | dicom | Database name for metadata |
| `POSTGRES_HOST` | host.docker.internal | PostgreSQL host (host machine) |
| `POSTGRES_PORT` | 5432 | PostgreSQL port |
| `POSTGRES_USER` | postgres | Database username |
| `POSTGRES_PASSWORD` | postgres | Database password |
| `WILDFLY_WAIT_FOR` | ldap:389 | Wait for LDAP before starting |
| `JAVA_OPTS` | (optional) | JVM options (memory, GC settings) |

### Port Mapping

| Container Port | Host Port | Protocol | Purpose |
|----------------|-----------|----------|---------|
| 8080 | 8080 | HTTP | DICOMweb, Management UI |
| 11112 | 11112 | DICOM | C-STORE, C-FIND, C-MOVE (optional) |
| 9990 | (not exposed) | HTTP | WildFly admin console |

### Resource Requirements

**Minimum**:
- CPU: 2 cores
- Memory: 4GB RAM
- Storage: 10GB (metadata only, images in MinIO)

**Recommended**:
- CPU: 4 cores
- Memory: 8GB RAM
- Storage: 50GB (includes temp files, logs)

**Production**:
- CPU: 8 cores
- Memory: 16GB RAM
- Storage: 100GB SSD

---

## Database Schema

### PostgreSQL Configuration

**Database**: `dicom`

**Schema Setup**:
```bash
cd docker/dcm4che
make setup-dicom-db
```

**Runs SQL Scripts**:
1. `10_create-psql.sql`: Create tables
2. `20_create-fk-index.sql`: Add foreign keys and indexes
3. `30_create-case-insensitive-index.sql`: Add case-insensitive indexes

### Core Tables

#### 1. `study` Table

**Purpose**: Study-level metadata

```sql
CREATE TABLE study (
    pk BIGSERIAL PRIMARY KEY,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    access_control_id VARCHAR(255),
    access_time TIMESTAMP,
    completeness INT NOT NULL,
    expiration_date VARCHAR(255),
    expiration_exporter_id VARCHAR(255),
    expiration_state INT NOT NULL,
    ext_retrieve_aet VARCHAR(255),
    failed_retrieves INT NOT NULL,
    modified_time TIMESTAMP,
    rejection_state INT NOT NULL,
    storage_ids TEXT,
    study_desc VARCHAR(255),
    study_date VARCHAR(255),
    study_time VARCHAR(255),
    accession_no VARCHAR(255),
    study_id VARCHAR(255),
    study_iuid VARCHAR(255) NOT NULL UNIQUE,
    ref_phys_name_json TEXT,
    ref_phys_name_ide_json TEXT,
    ref_phys_name_pho_json TEXT,
    study_custom1 VARCHAR(255),
    study_custom2 VARCHAR(255),
    study_custom3 VARCHAR(255),
    study_size BIGINT DEFAULT -1,
    patient_fk BIGINT NOT NULL REFERENCES patient(pk)
);

CREATE INDEX idx_study_iuid ON study(study_iuid);
CREATE INDEX idx_study_date ON study(study_date);
CREATE INDEX idx_study_patient_fk ON study(patient_fk);
```

**Key Columns**:
- `study_iuid`: DICOM StudyInstanceUID (unique)
- `study_desc`: Study description
- `study_date`: Study date (YYYYMMDD)
- `study_time`: Study time (HHMMSS)
- `accession_no`: Accession number (hospital identifier)
- `patient_fk`: Foreign key to patient table
- `storage_ids`: JSON array of storage systems
- `study_size`: Total size in bytes

#### 2. `series` Table

**Purpose**: Series-level metadata

```sql
CREATE TABLE series (
    pk BIGSERIAL PRIMARY KEY,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    body_part VARCHAR(255),
    completeness INT NOT NULL,
    expiration_date VARCHAR(255),
    expiration_exporter_id VARCHAR(255),
    expiration_state INT NOT NULL,
    ext_retrieve_aet VARCHAR(255),
    failed_retrieves INT NOT NULL,
    inst_purge_state INT NOT NULL,
    inst_purge_time TIMESTAMP,
    laterality VARCHAR(255),
    metadata_update_failures INT NOT NULL,
    metadata_update_time TIMESTAMP,
    modality VARCHAR(255),
    rejection_state INT NOT NULL,
    series_desc VARCHAR(255),
    series_no VARCHAR(255),
    series_iuid VARCHAR(255) NOT NULL UNIQUE,
    src_aet VARCHAR(255),
    station_name VARCHAR(255),
    storage_ids TEXT,
    storage_verify_time TIMESTAMP,
    tsuid VARCHAR(255),
    series_custom1 VARCHAR(255),
    series_custom2 VARCHAR(255),
    series_custom3 VARCHAR(255),
    series_size BIGINT DEFAULT -1,
    study_fk BIGINT NOT NULL REFERENCES study(pk)
);

CREATE INDEX idx_series_iuid ON series(series_iuid);
CREATE INDEX idx_series_study_fk ON series(study_fk);
CREATE INDEX idx_series_modality ON series(modality);
```

**Key Columns**:
- `series_iuid`: DICOM SeriesInstanceUID (unique)
- `series_desc`: Series description
- `series_no`: Series number (display order)
- `modality`: CR, CT, MR, US, etc.
- `body_part`: Anatomical region
- `laterality`: L (left), R (right), B (bilateral)
- `study_fk`: Foreign key to study table

#### 3. `instance` Table

**Purpose**: Instance (image) level metadata

```sql
CREATE TABLE instance (
    pk BIGSERIAL PRIMARY KEY,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    availability INT NOT NULL,
    completeness INT NOT NULL,
    content_date VARCHAR(255),
    content_time VARCHAR(255),
    ext_retrieve_aet VARCHAR(255),
    inst_custom1 VARCHAR(255),
    inst_custom2 VARCHAR(255),
    inst_custom3 VARCHAR(255),
    inst_no VARCHAR(255),
    rejection_state INT NOT NULL,
    sop_cuid VARCHAR(255) NOT NULL,
    sop_iuid VARCHAR(255) NOT NULL UNIQUE,
    sr_complete VARCHAR(255),
    sr_verified VARCHAR(255),
    storage_ids TEXT,
    storage_verify_time TIMESTAMP,
    inst_size BIGINT DEFAULT -1,
    series_fk BIGINT NOT NULL REFERENCES series(pk)
);

CREATE INDEX idx_instance_sop_iuid ON instance(sop_iuid);
CREATE INDEX idx_instance_series_fk ON instance(series_fk);
CREATE INDEX idx_instance_sop_cuid ON instance(sop_cuid);
```

**Key Columns**:
- `sop_iuid`: DICOM SOPInstanceUID (unique)
- `sop_cuid`: SOP Class UID (image type)
- `inst_no`: Instance number (display order)
- `inst_size`: File size in bytes
- `storage_ids`: JSON array of storage locations
- `series_fk`: Foreign key to series table

#### 4. `patient` Table

**Purpose**: Patient demographics

```sql
CREATE TABLE patient (
    pk BIGSERIAL PRIMARY KEY,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    num_studies INT NOT NULL DEFAULT 0,
    pat_birthdate VARCHAR(255),
    pat_custom1 VARCHAR(255),
    pat_custom2 VARCHAR(255),
    pat_custom3 VARCHAR(255),
    pat_id VARCHAR(255) NOT NULL,
    pat_id_issuer_json TEXT,
    pat_name_json TEXT,
    pat_name_ide_json TEXT,
    pat_name_pho_json TEXT,
    pat_sex VARCHAR(255),
    pat_size BIGINT DEFAULT -1,
    resp_person VARCHAR(255),
    resp_person_json TEXT,
    resp_person_ide_json TEXT,
    resp_person_pho_json TEXT,
    pat_verification_status INT NOT NULL,
    failed_verifications INT NOT NULL,
    verification_time TIMESTAMP,
    dicomattrs_fk BIGINT NOT NULL
);

CREATE INDEX idx_patient_id ON patient(pat_id);
CREATE INDEX idx_patient_name_json ON patient USING gin(pat_name_json jsonb_path_ops);
```

**Key Columns**:
- `pat_id`: Patient ID (hospital MRN)
- `pat_name_json`: Patient name (JSON format)
- `pat_birthdate`: Birth date (YYYYMMDD)
- `pat_sex`: M, F, O
- `num_studies`: Count of studies for patient

#### 5. `metadata` Table

**Purpose**: Bulk DICOM metadata storage

```sql
CREATE TABLE metadata (
    pk BIGSERIAL PRIMARY KEY,
    created_time TIMESTAMP NOT NULL,
    digest VARCHAR(255),
    object_size BIGINT NOT NULL,
    status INT NOT NULL,
    storage_id VARCHAR(255) NOT NULL,
    storage_path VARCHAR(255) NOT NULL
);

CREATE INDEX idx_metadata_storage_path ON metadata(storage_path);
CREATE INDEX idx_metadata_status ON metadata(status);
```

**Purpose**: Stores compressed DICOM metadata separately from images

---

## LDAP Configuration

### LDAP Schema

**Base DN**: `dc=dcm4che,dc=org`

**Device Entry**:
```
dn: dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
objectClass: dcmDevice
objectClass: dcmArchiveDevice
dicomDeviceName: dcm4chee-arc
dicomInstalled: TRUE
```

### Storage Configuration

**LDIF File**: `docker/dcm4che/bucketconfig.ldif`

```ldif
# Modify device to use MinIO storage
dn: dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
changetype: modify
replace: dcmStorageID
dcmStorageID: minio

# Add MinIO storage descriptor
dn: dcmStorageID=minio,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
changetype: add
objectClass: dcmStorage
dcmStorageID: minio
dcmURI: s3://dicom-bucket
dcmDigestAlgorithm: MD5
dcmInstanceAvailability: ONLINE
dcmStorageThreshold: 0
dcmProperty: pathStyleAccess=true
dcmProperty: endpoint=http://minio:9000
dcmProperty: accessKey=minioadmin
dcmProperty: secretKey=minioadmin
```

**Apply Configuration**:
```bash
cd docker/dcm4che
make ldap-setup
# Password: dcm4chee
```

**Storage Properties**:
- `pathStyleAccess=true`: Use path-style URLs (`http://minio:9000/dicom-bucket/key`)
- `endpoint`: MinIO API endpoint
- `accessKey` / `secretKey`: MinIO credentials

### AE Title Configuration

**Application Entity (AE)**: `DCM4CHEE`

**LDIF**:
```ldif
dn: dicomAETitle=DCM4CHEE,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
objectClass: dicomNetworkAE
objectClass: dcmNetworkAE
objectClass: dcmArchiveNetworkAE
dicomAETitle: DCM4CHEE
dicomAssociationAcceptor: TRUE
dicomAssociationInitiator: TRUE
dcmAcceptedUserRole: user
dcmAcceptedUserRole: admin
```

**Purpose**: DICOM network endpoint identifier

---

## DICOMweb API Reference

### Base URL Structure

```
http://{DCM4CHEE_HOST}:{PORT}/dcm4chee-arc/aets/{AE_TITLE}/{service}
```

**Example**:
```
http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies
```

### STOW-RS (Store Over the Web)

**Upload DICOM Instance**:

```http
POST /dcm4chee-arc/aets/DCM4CHEE/rs/studies HTTP/1.1
Content-Type: multipart/related; type="application/dicom"; boundary=BOUNDARY
Accept: application/dicom+json

--BOUNDARY
Content-Type: application/dicom

<DICOM binary data>
--BOUNDARY--
```

**Response (201 Created)**:
```json
{
  "00081190": {
    "vr": "UR",
    "Value": ["http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.2.840.113619..."]
  },
  "00081199": {
    "vr": "SQ",
    "Value": [
      {
        "00081150": {"vr": "UI", "Value": ["1.2.840.10008.5.1.4.1.1.7"]},
        "00081155": {"vr": "UI", "Value": ["1.2.840.113619..."]}
      }
    ]
  }
}
```

**Processing**:
1. Parse multipart/related body
2. Validate DICOM structure
3. Extract metadata (Study, Series, Instance UIDs)
4. Query LDAP for storage configuration
5. Store DICOM file in MinIO at:
   ```
   s3://dicom-bucket/studies/{StudyUID}/series/{SeriesUID}/{InstanceUID}.dcm
   ```
6. Insert metadata into PostgreSQL
7. Return JSON response with references

**Error Codes**:
- 200 OK: Success
- 202 Accepted: Async processing
- 409 Conflict: Instance already exists
- 400 Bad Request: Invalid DICOM
- 500 Internal Server Error: Storage failure

---

### QIDO-RS (Query based on ID)

#### Query All Studies

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/studies HTTP/1.1
Accept: application/dicom+json
```

**Query Parameters**:
| Parameter | Example | Description |
|-----------|---------|-------------|
| `StudyInstanceUID` | 1.2.840.113619... | Specific study |
| `PatientID` | MRN12345 | Patient identifier |
| `PatientName` | Doe^John | Patient name (wildcard: Doe*) |
| `StudyDate` | 20250416 | Exact date |
| `StudyDate` | 20250401-20250430 | Date range |
| `ModalitiesInStudy` | CT | Modality filter |
| `AccessionNumber` | ACC12345 | Accession number |
| `StudyDescription` | *Chest* | Wildcard search |
| `limit` | 50 | Max results (default: 100) |
| `offset` | 100 | Pagination offset |
| `includefield` | 00081030,00080061 | Extra DICOM tags |
| `fuzzymatching` | true | Fuzzy name matching |

**Example Query**:
```http
GET /rs/studies?PatientID=MRN12345&ModalitiesInStudy=CT&StudyDate=20250401-20250430&includefield=00081030 HTTP/1.1
```

**Response**:
```json
[
  {
    "0020000D": {"vr": "UI", "Value": ["1.2.840.113619.2.55.3.2609.2.1.1"]},
    "00080020": {"vr": "DA", "Value": ["20250416"]},
    "00080030": {"vr": "TM", "Value": ["103045"]},
    "00080050": {"vr": "SH", "Value": ["ACC12345"]},
    "00080061": {"vr": "CS", "Value": ["CT"]},
    "00081030": {"vr": "LO", "Value": ["CT Brain without Contrast"]},
    "00100010": {"vr": "PN", "Value": [{"Alphabetic": "Doe^John"}]},
    "00100020": {"vr": "LO", "Value": ["MRN12345"]},
    "00201206": {"vr": "IS", "Value": ["5"]},
    "00201208": {"vr": "IS", "Value": ["150"]}
  }
]
```

**Database Query (PostgreSQL)**:
```sql
SELECT DISTINCT
    s.study_iuid,
    s.study_date,
    s.study_time,
    s.accession_no,
    s.study_desc,
    p.pat_id,
    p.pat_name_json,
    COUNT(DISTINCT ser.pk) AS num_series,
    COUNT(inst.pk) AS num_instances
FROM study s
JOIN patient p ON s.patient_fk = p.pk
LEFT JOIN series ser ON ser.study_fk = s.pk
LEFT JOIN instance inst ON inst.series_fk = ser.pk
WHERE p.pat_id = 'MRN12345'
  AND ser.modality = 'CT'
  AND s.study_date BETWEEN '20250401' AND '20250430'
GROUP BY s.pk, p.pk
ORDER BY s.study_date DESC, s.study_time DESC
LIMIT 100 OFFSET 0;
```

---

#### Query Series for Study

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/studies/{StudyInstanceUID}/series HTTP/1.1
Accept: application/dicom+json
```

**Response**:
```json
[
  {
    "0020000E": {"vr": "UI", "Value": ["1.2.840.113619.2.55.3.2609.2.2.1"]},
    "0020000D": {"vr": "UI", "Value": ["1.2.840.113619.2.55.3.2609.2.1.1"]},
    "00080060": {"vr": "CS", "Value": ["CT"]},
    "0008103E": {"vr": "LO", "Value": ["Axial Brain"]},
    "00200011": {"vr": "IS", "Value": ["1"]},
    "00201209": {"vr": "IS", "Value": ["150"]}
  }
]
```

**Database Query**:
```sql
SELECT
    ser.series_iuid,
    ser.modality,
    ser.series_desc,
    ser.series_no,
    COUNT(inst.pk) AS num_instances
FROM series ser
LEFT JOIN instance inst ON inst.series_fk = ser.pk
WHERE ser.study_fk = (
    SELECT pk FROM study WHERE study_iuid = '1.2.840.113619.2.55.3.2609.2.1.1'
)
GROUP BY ser.pk
ORDER BY CAST(ser.series_no AS INTEGER);
```

---

#### Query Instances

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/instances?SOPInstanceUID={InstanceUID} HTTP/1.1
Accept: application/dicom+json
```

**Response**: Full DICOM metadata for instance

---

### WADO-RS (Web Access to DICOM Objects)

#### Retrieve Study

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/studies/{StudyInstanceUID} HTTP/1.1
Accept: multipart/related; type="application/dicom"
```

**Response**: Multipart message with all DICOM instances in study

---

#### Retrieve Series

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/studies/{StudyUID}/series/{SeriesUID} HTTP/1.1
Accept: multipart/related; type="application/dicom"
```

---

#### Retrieve Instance

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/studies/{StudyUID}/series/{SeriesUID}/instances/{InstanceUID} HTTP/1.1
Accept: application/dicom
```

**Response**: Single DICOM file (binary)

---

#### Retrieve Frames (for OHIF)

```http
GET /dcm4chee-arc/aets/DCM4CHEE/rs/studies/{StudyUID}/series/{SeriesUID}/instances/{InstanceUID}/frames/1 HTTP/1.1
Accept: image/jpeg
```

**Response**: JPEG image (rendered frame)

**OHIF Usage**:
```javascript
// OHIF fetches frame as JPEG for fast display
const frameUrl = `${DICOMWEB_ROOT}/studies/${studyUID}/series/${seriesUID}/instances/${instanceUID}/frames/1`;
```

**Processing Flow**:
1. DCM4CHEE receives frame request
2. Queries PostgreSQL for storage location
3. Retrieves DICOM file from MinIO
4. Extracts specified frame (multi-frame images)
5. Converts to JPEG (if Accept: image/jpeg)
6. Returns image data

---

### WADO-URI (Legacy)

```http
GET /dcm4chee-arc/aets/DCM4CHEE/wado?requestType=WADO&studyUID={StudyUID}&seriesUID={SeriesUID}&objectUID={InstanceUID} HTTP/1.1
```

**Purpose**: Legacy endpoint, WADO-RS preferred

---

## Management UI

### Access URL

```
http://localhost:8080/dcm4chee-arc/ui2
```

**Default Credentials**:
- Username: `admin`
- Password: `admin`

**Recommended**: Change password after first login

### UI Features

#### 1. Study Browser

**Path**: `/ui2/study`

**Features**:
- Search studies by patient, date, modality
- View thumbnails
- Download DICOM files
- Delete studies
- Export to external systems

**Screenshot Workflow**:
```
Search → Results Grid → Right-click Study → Actions:
  - View in OHIF
  - Download as ZIP
  - Export to AE Title
  - Delete Study
  - Reject Study
```

---

#### 2. Configuration

**Path**: `/ui2/device/devicelist`

**Sections**:
- **Devices**: Network configuration
- **AE Titles**: Application entities
- **Storage**: Storage descriptors (MinIO config)
- **Transfer Capabilities**: Supported DICOM SOP Classes
- **Queues**: Background task monitoring

**Edit Storage**:
```
Configuration → Devices → dcm4chee-arc → Storage Descriptors → minio
  - URI: s3://dicom-bucket
  - Properties: endpoint, accessKey, secretKey
  - Digest Algorithm: MD5
  - Instance Availability: ONLINE
```

---

#### 3. Monitoring

**Path**: `/ui2/monitoring/queues`

**Queue Types**:
- **Export**: Studies being exported
- **Retrieve**: Studies being retrieved
- **Diff**: Studies being compared
- **Storage Verification**: Integrity checks

**Metrics**:
- Queue length
- Processing rate
- Failures
- Scheduled vs completed

---

#### 4. Reject Notes

**Path**: `/ui2/reject`

**Purpose**: Mark studies as rejected (QA failures, duplicates)

**Rejection Codes**:
- Incorrect Modality Worklist Entry
- Data Retention Period Expired
- Duplicate Instance
- Quality Issues

**Effect**: Study hidden from searches, marked for deletion

---

## Storage Integration (MinIO)

### MinIO Configuration

**Bucket**: `dicom-bucket`

**Access**:
```bash
# MinIO Console
http://localhost:9000

# Credentials
Username: minioadmin
Password: minioadmin
```

### Object Key Structure

**Format**:
```
studies/{StudyInstanceUID}/series/{SeriesInstanceUID}/{SOPInstanceUID}.dcm
```

**Example**:
```
studies/1.2.840.113619.2.55.3.2609.2.1.1/
  series/1.2.840.113619.2.55.3.2609.2.2.1/
    1.2.840.113619.2.55.3.2609.2.3.1.dcm
    1.2.840.113619.2.55.3.2609.2.3.2.dcm
  series/1.2.840.113619.2.55.3.2609.2.2.2/
    1.2.840.113619.2.55.3.2609.2.3.3.dcm
```

### Storage Workflow

```
DICOM Upload (STOW-RS)
  ↓
DCM4CHEE validates and parses
  ↓
Query LDAP for storage config
  ↓
Generate S3 key from UIDs
  ↓
MinIO PUT /dicom-bucket/{key}
  ↓
MinIO stores object (versioned)
  ↓
MinIO returns ETag (MD5 hash)
  ↓
DCM4CHEE stores metadata in PostgreSQL:
  - storage_id: "minio"
  - storage_path: "studies/1.2.840..."
  ↓
DCM4CHEE returns success to client
```

### Storage Verification

**Scheduled Task**: Every 24 hours

**Process**:
1. Query PostgreSQL for instances to verify
2. For each instance:
   - Retrieve ETag from MinIO (`HEAD` request)
   - Compare with stored MD5 digest
   - Update `storage_verify_time` timestamp
3. Flag mismatches for repair

**Manual Trigger**:
```bash
curl -X POST http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/stgver/minio
```

---

## Performance Tuning

### WildFly JVM Options

**Environment Variable**: `JAVA_OPTS`

```yaml
environment:
  JAVA_OPTS: >
    -Xms4g
    -Xmx8g
    -XX:MetaspaceSize=256m
    -XX:MaxMetaspaceSize=512m
    -XX:+UseG1GC
    -XX:MaxGCPauseMillis=200
```

**Explanation**:
- `-Xms4g`: Initial heap size (4GB)
- `-Xmx8g`: Maximum heap size (8GB)
- `-XX:+UseG1GC`: Use G1 garbage collector (better for large heaps)
- `-XX:MaxGCPauseMillis=200`: Target max GC pause (200ms)

### PostgreSQL Tuning

**postgresql.conf**:
```ini
# Memory
shared_buffers = 2GB
effective_cache_size = 8GB
work_mem = 64MB
maintenance_work_mem = 512MB

# Connections
max_connections = 200

# Query Planner
random_page_cost = 1.1  # SSD
effective_io_concurrency = 200

# Write Ahead Log
wal_buffers = 16MB
checkpoint_completion_target = 0.9
```

### Index Optimization

**Add Custom Indexes**:
```sql
-- Optimize patient search by name
CREATE INDEX idx_patient_name_lower ON patient(LOWER(pat_name_json->>'Alphabetic'));

-- Optimize study search by date range
CREATE INDEX idx_study_date_brin ON study USING brin(study_date);

-- Optimize series count
CREATE INDEX idx_series_study_covering ON series(study_fk) INCLUDE (pk, modality);
```

### Connection Pooling

**WildFly DataSource**:
```xml
<datasource jndi-name="java:jboss/datasources/PostgresDS">
    <connection-url>jdbc:postgresql://host.docker.internal:5432/dicom</connection-url>
    <driver>postgresql</driver>
    <pool>
        <min-pool-size>10</min-pool-size>
        <max-pool-size>100</max-pool-size>
        <prefill>true</prefill>
    </pool>
</datasource>
```

---

## Monitoring and Logging

### Log Files

**Location**: `/opt/wildfly/standalone/log/`

**Files**:
- `server.log`: General application logs
- `dcm4chee-arc.log`: DCM4CHEE specific logs
- `access.log`: HTTP access logs (if enabled)

**View Logs**:
```bash
docker exec -it care_radiology-arc-1 tail -f /opt/wildfly/standalone/log/server.log
```

**Log Level Configuration**:
```bash
# Via Management UI: Configuration → Logging → Root Logger
# Or via CLI:
docker exec -it care_radiology-arc-1 \
  /opt/wildfly/bin/jboss-cli.sh \
  --connect \
  --command='/subsystem=logging/root-logger=ROOT:write-attribute(name=level,value=DEBUG)'
```

### Prometheus Metrics

**Endpoint**: `http://localhost:8080/dcm4chee-arc/metrics`

**Metrics Exposed**:
- `dcm4chee_studies_total`: Total studies stored
- `dcm4chee_series_total`: Total series stored
- `dcm4chee_instances_total`: Total instances stored
- `dcm4chee_storage_size_bytes`: Total storage used
- `dcm4chee_queue_size`: Queue lengths
- `http_requests_total`: HTTP request count
- `http_request_duration_seconds`: Request latency

**Prometheus Config**:
```yaml
scrape_configs:
  - job_name: 'dcm4chee'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/dcm4chee-arc/metrics'
```

---

## Troubleshooting

### Common Issues

#### 1. Container Won't Start

**Symptoms**:
```
arc-1  | Waiting for LDAP at ldap:389...
arc-1  | Connection refused
```

**Solution**:
```bash
# Check LDAP is running
docker ps | grep ldap

# Check WILDFLY_WAIT_FOR
docker inspect care_radiology-arc-1 | grep WILDFLY_WAIT_FOR
```

---

#### 2. Database Connection Failure

**Symptoms**:
```
ERROR [org.jboss.jca.core.connectionmanager.pool.strategy.OnePool] IJ000604:
Throwable while attempting to get a new connection: null:
org.postgresql.util.PSQLException: Connection to localhost:5432 refused
```

**Solution**:
```bash
# Verify PostgreSQL is accessible from container
docker exec care_radiology-arc-1 nc -zv host.docker.internal 5432

# Check environment variables
docker exec care_radiology-arc-1 env | grep POSTGRES
```

---

#### 3. Storage Upload Failure

**Symptoms**:
```
ERROR [org.dcm4chee.arc.storage.AbstractStorage] Failed to store instance:
java.io.IOException: Unable to connect to S3 endpoint
```

**Solutions**:
1. **Check LDAP storage config**:
   ```bash
   ldapsearch -x -D "cn=admin,dc=dcm4che,dc=org" \
     -H ldap://localhost:3890 -W \
     -b "dcmStorageID=minio,dicomDeviceName=dcm4chee-arc,..." \
     dcmProperty
   ```

2. **Verify MinIO connectivity**:
   ```bash
   docker exec care_radiology-arc-1 curl http://minio:9000
   ```

3. **Check bucket exists**:
   ```bash
   # In MinIO console, verify dicom-bucket exists
   ```

---

#### 4. Slow Query Performance

**Symptoms**: QIDO-RS queries take >5 seconds

**Diagnosis**:
```sql
-- Enable query logging
ALTER DATABASE dicom SET log_statement = 'all';
ALTER DATABASE dicom SET log_duration = on;

-- Check slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

**Solutions**:
- Add missing indexes
- Increase `work_mem`
- Vacuum tables
- Update statistics: `ANALYZE study, series, instance;`

---

## Security Considerations

### Authentication

**Management UI**:
- Change default password
- Enable HTTPS (reverse proxy)
- Restrict network access

**DICOMweb API**:
- Current: No authentication (behind nginx)
- Recommended: Add OAuth 2.0 or API key

### Data Protection

1. **Encryption at Rest**:
   - MinIO: Server-side encryption (SSE-S3 or SSE-KMS)
   - PostgreSQL: Transparent data encryption (TDE)

2. **Encryption in Transit**:
   - HTTPS for DICOMweb (nginx with SSL)
   - TLS for PostgreSQL connection

3. **Access Control**:
   - Network segmentation (private subnets)
   - Firewall rules (port 8080 not public)
   - Role-based access in UI

### Compliance

**HIPAA Requirements**:
- ✓ Audit logs (PostgreSQL + WildFly logs)
- ✓ Access control (user authentication)
- ✓ Encryption (TLS + at-rest)
- ✓ Integrity verification (MD5 digests)

---

## Related Documentation

- [OHIF_INTEGRATION.md](./OHIF_INTEGRATION.md) - OHIF viewer integration
- [MINIO_STORAGE.md](./MINIO_STORAGE.md) - Object storage details
- [LDAP_CONFIGURATION.md](./LDAP_CONFIGURATION.md) - LDAP schema reference
- [API_UPLOAD_ENDPOINT.md](./API_UPLOAD_ENDPOINT.md) - Upload flow

---

*Document Version: 1.0*
*Last Updated: 2025-04-16*
*Maintained by: Care Development Team*
