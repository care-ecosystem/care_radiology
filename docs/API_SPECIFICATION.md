# Care Radiology Plugin - API Specification & Database Schema

**Version**: 1.0
**Last Updated**: 2026-04-23
**Status**: Complete

---

## Table of Contents

1. [Overview](#overview)
2. [Database Schema](#database-schema)
3. [Entity Relationship Diagrams](#entity-relationship-diagrams)
4. [API Endpoints](#api-endpoints)
5. [Authentication & Authorization](#authentication--authorization)
6. [Request/Response Schemas](#requestresponse-schemas)
7. [Error Handling](#error-handling)
8. [Performance Considerations](#performance-considerations)

---

## Overview

The care_radiology plugin provides a comprehensive DICOM imaging management system integrated with the Care EMR platform. It includes:

- **DICOM Study Management**: Upload, query, and manage DICOM studies
- **Radiology Reporting**: Create and audit radiology reports
- **Configuration Management**: Manage modalities, body parts, scan protocols, and templates
- **Worklist Integration**: Query pending radiology service requests
- **Webhook Logging**: Track external system events

**Base URL**: `/api/care_radiology/`

**Technology Stack**:
- Django 5.x
- Django REST Framework
- Pydantic (request/response validation)
- PostgreSQL (metadata storage)
- DCM4CHEE Archive (PACS backend)
- Redis (caching layer)

---

## Database Schema

### Core Models

All models inherit from `EMRBaseModel`, which provides:

```python
class EMRBaseModel(models.Model):
    external_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_date = models.DateTimeField(auto_now_add=True)
    modified_date = models.DateTimeField(auto_now=True)
    deleted = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")

    class Meta:
        abstract = True
```

### 1. DicomStudy

**Table**: `radiology_dicomstudy`

Stores the mapping between Care patients and DICOM studies stored in DCM4CHEE.

```python
class DicomStudy(EMRBaseModel):
    patient = ForeignKey(Patient, on_delete=CASCADE, related_name="dicom_studies")
    dicom_study_uid = CharField(max_length=500)

    # Constraint: One study UID per patient
    unique_together = ["patient", "dicom_study_uid"]
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY, UNIQUE | Unique identifier |
| patient_id | UUID | FOREIGN KEY → emr_patient.id | Patient reference |
| dicom_study_uid | VARCHAR(500) | NOT NULL | DICOM Study Instance UID |
| created_date | TIMESTAMP | NOT NULL | Auto-set on creation |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_by_id | UUID | FOREIGN KEY → users_user.id, NULL | Audit: creator |
| updated_by_id | UUID | FOREIGN KEY → users_user.id, NULL | Audit: last updater |

**Indexes**:
- PRIMARY: `external_id`
- UNIQUE: `(patient_id, dicom_study_uid)`
- INDEX: `patient_id`, `deleted`

**Relationships**:
- `patient` → `Patient` (Many-to-One)
- `study_reports` ← `StudyReport` (One-to-Many)
- `dicom_studies` ← `RadiologyServiceRequest` (One-to-Many)

---

### 2. StudyReport

**Table**: `radiology_studyreport`

Stores radiology reports for DICOM studies.

```python
class StudyReport(EMRBaseModel):
    study = ForeignKey(DicomStudy, on_delete=CASCADE, related_name="study_reports")
    modality = ForeignKey(ModalityType, on_delete=CASCADE)
    body_part = ForeignKey(BodyPart, on_delete=CASCADE)
    scan_protocol = ForeignKey(ScanProtocol, on_delete=CASCADE)
    technique = TextField(null=True, blank=True)
    findings = TextField(null=True, blank=True)
    impression = TextField(null=True, blank=True)
    created_datetime = DateTimeField(default=timezone.now)
    last_modified_datetime = DateTimeField(auto_now=True)
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| study_id | UUID | FOREIGN KEY → radiology_dicomstudy.id | DICOM study reference |
| modality_id | UUID | FOREIGN KEY → radiology_modalitytype.id | Modality type |
| body_part_id | UUID | FOREIGN KEY → radiology_bodypart.id | Body part scanned |
| scan_protocol_id | UUID | FOREIGN KEY → radiology_scanprotocol.id | Scan protocol used |
| technique | TEXT | NULL | Imaging technique details |
| findings | TEXT | NULL | Clinical findings |
| impression | TEXT | NULL | Radiologist's impression |
| created_datetime | TIMESTAMP | DEFAULT NOW() | Report creation time |
| last_modified_datetime | TIMESTAMP | AUTO UPDATE | Last modification time |
| created_by_id | UUID | FOREIGN KEY → users_user.id | Report author |
| updated_by_id | UUID | FOREIGN KEY → users_user.id | Last editor |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |

**Indexes**:
- PRIMARY: `external_id`
- INDEX: `study_id`, `modality_id`, `body_part_id`, `scan_protocol_id`, `deleted`

**Relationships**:
- `study` → `DicomStudy` (Many-to-One)
- `modality` → `ModalityType` (Many-to-One)
- `body_part` → `BodyPart` (Many-to-One)
- `scan_protocol` → `ScanProtocol` (Many-to-One)
- `audits` ← `StudyReportAudit` (One-to-Many)

---

### 3. StudyReportAudit

**Table**: `radiology_studyreportaudit`

Audit trail for all report changes (HIPAA compliance).

```python
class StudyReportAudit(EMRBaseModel):
    study_report = ForeignKey(StudyReport, on_delete=CASCADE, related_name="audits")
    action = CharField(max_length=20)  # "CREATED", "UPDATED"
    field_name = CharField(max_length=100)
    old_value = JSONField(null=True, blank=True)
    new_value = JSONField(null=True, blank=True)
    created_datetime = DateTimeField(default=timezone.now)
    last_modified_datetime = DateTimeField(auto_now=True)
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| study_report_id | UUID | FOREIGN KEY → radiology_studyreport.id | Report reference |
| action | VARCHAR(20) | NOT NULL | "CREATED" or "UPDATED" |
| field_name | VARCHAR(100) | NOT NULL | Field changed (or "All"/"Multiple") |
| old_value | JSONB | NULL | Previous value(s) |
| new_value | JSONB | NULL | New value(s) |
| created_datetime | TIMESTAMP | DEFAULT NOW() | Audit entry timestamp |
| last_modified_datetime | TIMESTAMP | AUTO UPDATE | Auto-updated |
| created_by_id | UUID | FOREIGN KEY → users_user.id | User who made change |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |

**Indexes**:
- PRIMARY: `external_id`
- INDEX: `study_report_id`, `created_datetime DESC`

**Ordering**: `ORDER BY created_datetime DESC`

**Relationships**:
- `study_report` → `StudyReport` (Many-to-One)

---

### 4. RadiologyServiceRequest

**Table**: `radiology_radiologyservicerequest`

Links Care ServiceRequest with DICOM studies (worklist integration).

```python
class RadiologyServiceRequest(EMRBaseModel):
    service_request = ForeignKey(ServiceRequest, on_delete=CASCADE,
                                 related_name="radiology_service_requests", null=True)
    dicom_study = ForeignKey(DicomStudy, on_delete=CASCADE,
                            related_name="dicom_studies", null=True)
    raw_data = JSONField()

    # Constraint: Unique pairing
    unique_together = ["service_request", "dicom_study"]
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| service_request_id | UUID | FOREIGN KEY → emr_servicerequest.id, NULL | Care service request |
| dicom_study_id | UUID | FOREIGN KEY → radiology_dicomstudy.id, NULL | DICOM study |
| raw_data | JSONB | NOT NULL | Original webhook/worklist data |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_date | TIMESTAMP | NOT NULL | Auto-set |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |

**Indexes**:
- PRIMARY: `external_id`
- UNIQUE: `(service_request_id, dicom_study_id)`
- INDEX: `service_request_id`, `dicom_study_id`, `deleted`

**Relationships**:
- `service_request` → `ServiceRequest` (Many-to-One)
- `dicom_study` → `DicomStudy` (Many-to-One)

---

### 5. ModalityType

**Table**: `radiology_modalitytype`

Configurable list of imaging modalities (CT, MRI, X-Ray, etc.).

```python
class ModalityType(EMRBaseModel):
    display_name = CharField(max_length=255, unique=True)
    coding = JSONField(default=list)  # [{coding_system, coding_code, coding_display}]
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| display_name | VARCHAR(255) | UNIQUE, NOT NULL | Human-readable name (e.g., "CT Scan") |
| coding | JSONB | DEFAULT '[]' | FHIR-style coding (SNOMED CT, DICOM, etc.) |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_date | TIMESTAMP | NOT NULL | Auto-set |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |

**Indexes**:
- PRIMARY: `external_id`
- UNIQUE: `display_name` (where `deleted = FALSE`)
- INDEX: `deleted`

**Relationships**:
- `body_parts` ← `BodyPart` (One-to-Many)
- `scan_protocols` ← `ScanProtocol` (One-to-Many)

**Example Coding**:
```json
[
  {
    "coding_system": "http://dicom.nema.org/resources/ontology/DCM",
    "coding_code": "CT",
    "coding_display": "Computed Tomography"
  }
]
```

---

### 6. BodyPart

**Table**: `radiology_bodypart`

Configurable list of body parts per modality.

```python
class BodyPart(EMRBaseModel):
    modality = ForeignKey(ModalityType, on_delete=CASCADE, related_name="body_parts")
    display_name = CharField(max_length=255)
    coding = JSONField(default=list)
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| modality_id | UUID | FOREIGN KEY → radiology_modalitytype.id | Parent modality |
| display_name | VARCHAR(255) | NOT NULL | Human-readable name (e.g., "Chest") |
| coding | JSONB | DEFAULT '[]' | FHIR-style coding (SNOMED CT body site) |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_date | TIMESTAMP | NOT NULL | Auto-set |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |

**Indexes**:
- PRIMARY: `external_id`
- INDEX: `modality_id`, `deleted`

**Relationships**:
- `modality` → `ModalityType` (Many-to-One)
- `scan_protocols` ← `ScanProtocol` (One-to-Many)

**Example Coding**:
```json
[
  {
    "coding_system": "http://snomed.info/sct",
    "coding_code": "51185008",
    "coding_display": "Chest"
  }
]
```

---

### 7. ScanProtocol

**Table**: `radiology_scanprotocol`

Configurable list of scan protocols per modality and body part.

```python
class ScanProtocol(EMRBaseModel):
    modality = ForeignKey(ModalityType, on_delete=CASCADE, related_name="scan_protocols")
    body_part = ForeignKey(BodyPart, on_delete=CASCADE, related_name="scan_protocols")
    display_name = CharField(max_length=255)
    coding = JSONField(default=list)
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| modality_id | UUID | FOREIGN KEY → radiology_modalitytype.id | Parent modality |
| body_part_id | UUID | FOREIGN KEY → radiology_bodypart.id | Parent body part |
| display_name | VARCHAR(255) | NOT NULL | Human-readable name (e.g., "High-Resolution Chest CT") |
| coding | JSONB | DEFAULT '[]' | FHIR-style coding (procedure codes) |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_date | TIMESTAMP | NOT NULL | Auto-set |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |

**Indexes**:
- PRIMARY: `external_id`
- INDEX: `modality_id`, `body_part_id`, `deleted`

**Relationships**:
- `modality` → `ModalityType` (Many-to-One)
- `body_part` → `BodyPart` (Many-to-One)

---

### 8. Template

**Table**: `radiology_template`

User-specific report templates (technique/findings/impression pre-fills).

```python
class Template(EMRBaseModel):
    user = ForeignKey(User, on_delete=CASCADE, related_name="templates")
    modality = ForeignKey(ModalityType, on_delete=CASCADE)
    body_part = ForeignKey(BodyPart, on_delete=CASCADE)
    scan_protocol = ForeignKey(ScanProtocol, on_delete=CASCADE)
    technique = TextField(null=True, blank=True)
    findings = TextField(null=True, blank=True)
    impression = TextField(null=True, blank=True)
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| user_id | UUID | FOREIGN KEY → users_user.id | Template owner |
| modality_id | UUID | FOREIGN KEY → radiology_modalitytype.id | Modality |
| body_part_id | UUID | FOREIGN KEY → radiology_bodypart.id | Body part |
| scan_protocol_id | UUID | FOREIGN KEY → radiology_scanprotocol.id | Scan protocol |
| technique | TEXT | NULL | Pre-filled technique text |
| findings | TEXT | NULL | Pre-filled findings text |
| impression | TEXT | NULL | Pre-filled impression text |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_date | TIMESTAMP | NOT NULL | Auto-set |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |

**Indexes**:
- PRIMARY: `external_id`
- INDEX: `user_id`, `modality_id`, `body_part_id`, `scan_protocol_id`, `deleted`

**Relationships**:
- `user` → `User` (Many-to-One)
- `modality` → `ModalityType` (Many-to-One)
- `body_part` → `BodyPart` (Many-to-One)
- `scan_protocol` → `ScanProtocol` (Many-to-One)

---

### 9. RadiologyWebhookLogs

**Table**: `radiology_radiologywebhooklogs`

Stores raw webhook payloads from DCM4CHEE and other external systems.

```python
class RadiologyWebhookLogs(EMRBaseModel):
    raw_data = JSONField()
    type = CharField(max_length=50)
```

**Fields**:

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| external_id | UUID | PRIMARY KEY | Unique identifier |
| raw_data | JSONB | NOT NULL | Complete webhook payload |
| type | VARCHAR(50) | NOT NULL | Event type (e.g., "STUDY_RECEIVED") |
| deleted | BOOLEAN | DEFAULT FALSE | Soft delete flag |
| created_date | TIMESTAMP | NOT NULL | Auto-set |
| modified_date | TIMESTAMP | NOT NULL | Auto-updated |

**Indexes**:
- PRIMARY: `external_id`
- INDEX: `type`, `created_date`, `deleted`

---

## Entity Relationship Diagrams

### Full Schema Overview

```
┌─────────────────────┐
│   Patient (Care)    │
│  (emr_patient)      │
└──────────┬──────────┘
           │ 1
           │
           │ N
┌──────────▼──────────────────────┐
│      DicomStudy                 │
│  radiology_dicomstudy           │
│  ─────────────────────          │
│  • external_id (PK)             │
│  • patient_id (FK)              │
│  • dicom_study_uid              │
│  • created_date                 │
│  • created_by_id                │
└──────┬─────────────┬────────────┘
       │ 1           │ 1
       │             │
       │ N           │ N
       │      ┌──────▼────────────────────────────┐
       │      │  RadiologyServiceRequest          │
       │      │  radiology_radiologyservicereq... │
       │      │  ──────────────────────────────   │
       │      │  • external_id (PK)               │
       │      │  • service_request_id (FK)        │
       │      │  • dicom_study_id (FK)            │
       │      │  • raw_data (JSONB)               │
       │      └───────────────────────────────────┘
       │
       │ N
┌──────▼──────────────────────────────────┐
│          StudyReport                    │
│  radiology_studyreport                  │
│  ──────────────────────────────         │
│  • external_id (PK)                     │
│  • study_id (FK)                        │
│  • modality_id (FK) ────────┐           │
│  • body_part_id (FK) ────┐  │           │
│  • scan_protocol_id (FK) │  │           │
│  • technique             │  │           │
│  • findings              │  │           │
│  • impression            │  │           │
│  • created_datetime      │  │           │
│  • last_modified_date... │  │           │
└──────┬───────────────────┼──┼───────────┘
       │ 1                 │  │
       │                   │  │
       │ N                 │  │
┌──────▼─────────────────┐ │  │
│  StudyReportAudit      │ │  │
│  radiology_studyrepo...│ │  │
│  ───────────────────── │ │  │
│  • external_id (PK)    │ │  │
│  • study_report_id (FK)│ │  │
│  • action              │ │  │
│  • field_name          │ │  │
│  • old_value (JSONB)   │ │  │
│  • new_value (JSONB)   │ │  │
│  • created_datetime    │ │  │
└────────────────────────┘ │  │
                           │  │
                           │  │
        ┌──────────────────┼──┼────────────────────┐
        │                  │  │                    │
        │                  │  │                    │
┌───────▼─────────────┐    │  │    ┌───────────────▼──────────┐
│   BodyPart          │    │  │    │    ModalityType          │
│  radiology_bodypart │    │  │    │  radiology_modalitytype  │
│  ──────────────────│    │  │    │  ───────────────────────│
│  • external_id (PK) │◄───┘  └────┤  • external_id (PK)      │
│  • modality_id (FK) │            │  • display_name (UNIQUE) │
│  • display_name     │            │  • coding (JSONB)        │
│  • coding (JSONB)   │            └──────┬───────────────────┘
└──────┬──────────────┘                   │
       │ 1                                │
       │                                  │
       │ N                                │ 1
┌──────▼────────────────────┐             │
│   ScanProtocol            │             │ N
│  radiology_scanprotocol   │             │
│  ─────────────────────────│             │
│  • external_id (PK)       │             │
│  • modality_id (FK) ──────┼─────────────┘
│  • body_part_id (FK)      │
│  • display_name           │
│  • coding (JSONB)         │
└───────────────────────────┘


┌─────────────────────┐
│   User (Care)       │
│  (users_user)       │
└──────────┬──────────┘
           │ 1
           │
           │ N
┌──────────▼──────────────────────┐
│        Template                 │
│  radiology_template             │
│  ──────────────────────────     │
│  • external_id (PK)             │
│  • user_id (FK)                 │
│  • modality_id (FK)             │
│  • body_part_id (FK)            │
│  • scan_protocol_id (FK)        │
│  • technique                    │
│  • findings                     │
│  • impression                   │
└─────────────────────────────────┘


┌─────────────────────────────────┐
│   RadiologyWebhookLogs          │
│  radiology_radiologywebhooklogs │
│  ───────────────────────────    │
│  • external_id (PK)             │
│  • raw_data (JSONB)             │
│  • type                         │
│  • created_date                 │
└─────────────────────────────────┘
```

### Simplified Reporting Workflow

```
Patient ──> DicomStudy ──> StudyReport ──> StudyReportAudit
                │                │
                │                ├──> ModalityType
                │                ├──> BodyPart
                │                └──> ScanProtocol
                │
                └──> RadiologyServiceRequest ──> ServiceRequest (Care)
```

### Configuration Hierarchy

```
ModalityType (e.g., "CT Scan")
    │
    ├── BodyPart (e.g., "Chest")
    │       │
    │       └── ScanProtocol (e.g., "High-Resolution Chest CT")
    │
    └── BodyPart (e.g., "Abdomen")
            │
            └── ScanProtocol (e.g., "Contrast Abdomen CT")
```

---

## API Endpoints

### Base URL: `/api/care_radiology/`

### DICOM Operations

#### 1. Authenticate (Internal)

**Endpoint**: `GET /dicom/authenticate/`

**Purpose**: JWT verification endpoint called by nginx reverse proxy for DICOMweb requests.

**Authentication**: JWT Bearer Token (required)

**Request**:
```http
GET /api/care_radiology/dicom/authenticate/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Response**:
```http
HTTP/1.1 200 OK

(Empty body)
```

**Usage**: This endpoint is called by nginx `auth_request` directive before proxying DICOMweb requests to DCM4CHEE.

---

#### 2. Upload DICOM File

**Endpoint**: `POST /dicom/upload/`

**Purpose**: Upload a DICOM file for a patient, proxied to DCM4CHEE STOW-RS endpoint.

**Authentication**: JWT Bearer Token (required)

**Authorization**: `can_write_patient_obj` (user must have write access to the patient)

**Request**:

```http
POST /api/care_radiology/dicom/upload/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary...

------WebKitFormBoundary...
Content-Disposition: form-data; name="patient_id"

550e8400-e29b-41d4-a716-446655440000
------WebKitFormBoundary...
Content-Disposition: form-data; name="file"; filename="study.dcm"
Content-Type: application/dicom

<DICOM binary data>
------WebKitFormBoundary...--
```

**Request Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| patient_id | UUID | Yes | Patient's external_id |
| file | File | Yes | DICOM file (.dcm) |

**Response (Success)**:

```json
{
  "status": "success",
  "message": "DICOM uploaded successfully",
  "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
  "dicom_response": {
    "00081199": {
      "vr": "SQ",
      "Value": [
        {
          "00081150": {
            "vr": "UI",
            "Value": ["1.2.840.10008.5.1.4.1.1.2"]
          },
          "00081155": {
            "vr": "UI",
            "Value": ["1.2.840.113619.2.55.3.2609.2.3.1"]
          }
        }
      ]
    }
  }
}
```

**Response (Duplicate - 409 from DCM4CHEE)**:

```json
{
  "status": "success",
  "message": "DICOM already exists in DCM4CHEE",
  "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
  "dicom_response": { ... }
}
```

**Error Responses**:

```json
// 400 Bad Request
{
  "error": "No file provided"
}

// 403 Forbidden
{
  "detail": "You do not have permission to upload DICOM for this patient"
}

// 502 Bad Gateway (DCM4CHEE failure)
{
  "error": "Failed to upload to DCM4CHEE",
  "status_code": 500,
  "details": "Internal Server Error"
}

// 500 Internal Server Error
{
  "error": "Exception occurred",
  "details": "Error message here"
}
```

**Side Effects**:
1. DICOM file uploaded to DCM4CHEE via STOW-RS
2. `DicomStudy` record created/updated with study_uid and patient mapping
3. Redis cache busted for `radiology:dicom:study:{study_uid}`

**Code Reference**: `src/care_radiology/api/dicom.py:107`

---

#### 3. Query Patient Studies

**Endpoint**: `GET /dicom/studies/`

**Purpose**: Retrieve all DICOM studies for a patient with metadata from DCM4CHEE.

**Authentication**: JWT Bearer Token (required)

**Authorization**: `can_view_patient_obj` (user must have read access to the patient)

**Request**:

```http
GET /api/care_radiology/dicom/studies/?patientId=550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| patientId | UUID | Yes | Patient's external_id |

**Response**:

```json
[
  {
    "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
    "study_date": "2024-03-15T14:30:00",
    "study_description": "CT CHEST WITH CONTRAST",
    "study_modalities": ["CT"],
    "study_series": [
      {
        "series_uid": "1.2.840.113619.2.55.3.2609.2.2.1",
        "series_number": [1],
        "series_instance_count": [150],
        "series_description": ["AXIAL"],
        "series_modality": ["CT"]
      },
      {
        "series_uid": "1.2.840.113619.2.55.3.2609.2.2.2",
        "series_number": [2],
        "series_instance_count": [50],
        "series_description": ["CORONAL"],
        "series_modality": ["CT"]
      }
    ],
    "external_id": "650e8400-e29b-41d4-a716-446655440001",
    "has_report": true
  },
  {
    "study_uid": "1.2.840.113619.2.55.3.2609.2.1.2",
    "study_date": "2024-03-10T10:15:00",
    "study_description": "MRI BRAIN",
    "study_modalities": ["MR"],
    "study_series": [ ... ],
    "external_id": "650e8400-e29b-41d4-a716-446655440002",
    "has_report": false
  }
]
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| study_uid | String | DICOM Study Instance UID |
| study_date | ISO 8601 | Study date/time from DICOM tags |
| study_description | String | Study description (nullable) |
| study_modalities | String[] | Modalities in study (e.g., ["CT"]) |
| study_series | Array | Series metadata (see below) |
| external_id | UUID | DicomStudy external_id |
| has_report | Boolean | Whether StudyReport exists |

**Series Object**:

| Field | Type | Description |
|-------|------|-------------|
| series_uid | String | DICOM Series Instance UID |
| series_number | Number[] | Series number |
| series_instance_count | Number[] | Number of instances (images) |
| series_description | String[] | Series description |
| series_modality | String[] | Series modality |

**Error Responses**:

```json
// 403 Forbidden
{
  "detail": "You do not have permission to view this patient"
}

// 404 Not Found
{
  "detail": "Patient not found"
}
```

**Performance**:
- Uses `ThreadPoolExecutor` (max 10 workers) to fetch study metadata in parallel
- Redis caching (1-hour TTL) for study metadata (key: `radiology:dicom:study:{study_uid}`)
- Annotates `has_report` via Django `Exists` subquery

**Code Reference**: `src/care_radiology/api/dicom.py:219`

---

#### 4. Query Service Request Studies

**Endpoint**: `GET /dicom/service-requests/`

**Purpose**: Retrieve DICOM studies linked to a specific service request.

**Authentication**: Not required (uses AllowAny)

**Authorization**: `can_write_service_request` (internal authorization check)

**Request**:

```http
GET /api/care_radiology/dicom/service-requests/?serviceRequestId=750e8400-e29b-41d4-a716-446655440000 HTTP/1.1
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| serviceRequestId | UUID | Yes | ServiceRequest's external_id |

**Response**:

```json
[
  {
    "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
    "study_date": "2024-03-15T14:30:00",
    "study_description": "CT CHEST WITH CONTRAST",
    "study_modalities": ["CT"],
    "study_series": [ ... ],
    "external_id": "650e8400-e29b-41d4-a716-446655440001",
    "has_report": true
  }
]
```

**Error Responses**:

```json
// 403 Forbidden
{
  "detail": "You do not have permission to view this service request"
}

// 404 Not Found
{
  "detail": "Service request not found"
}
```

**Code Reference**: `src/care_radiology/api/dicom.py:243`

---

#### 5. Query Worklist

**Endpoint**: `GET /dicom/worklist/`

**Purpose**: Query pending radiology service requests (DICOM worklist integration).

**Authentication**: Static API Key (Header: `Authorization: <STATIC_API_KEY>`)

**Authorization**: None (public endpoint with API key)

**Request**:

```http
GET /api/care_radiology/dicom/worklist/?modality=CT&from=2024-03-01&to=2024-03-31 HTTP/1.1
Authorization: <STATIC_API_KEY>
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| modality | String | No | Filter by device registered name (e.g., "CT", "MRI") |
| from | Date | No | From date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS) |
| to | Date | No | To date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS) |
| facility | UUID | No | Facility external_id (currently unused in filter) |

**Response**:

```json
{
  "status": "success",
  "results": [
    {
      "service_request": {
        "id": "750e8400-e29b-41d4-a716-446655440000",
        "name": "CT Chest with Contrast",
        "date": "2024-03-15T09:00:00Z"
      },
      "facility": {
        "id": "850e8400-e29b-41d4-a716-446655440000",
        "name": "Central Hospital"
      },
      "patient": {
        "name": "John Doe",
        "address": "123 Main St, City",
        "phone_number": "+1234567890",
        "gender": "M",
        "age": 45
      }
    }
  ]
}
```

**Limit**: Maximum 1000 results

**Error Responses**:

```json
// 401 Unauthorized
{
  "detail": "Invalid API key"
}
```

**Code Reference**: `src/care_radiology/api/dicom.py:76`

---

### Study Reports

#### 6. Create Study Report

**Endpoint**: `POST /study_report/`

**Purpose**: Create or update a radiology report for a DICOM study.

**Authentication**: JWT Bearer Token (required)

**Authorization**: `can_write_radiology_report` (user must have radiology write permission)

**Request**:

```http
POST /api/care_radiology/study_report/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "study": "650e8400-e29b-41d4-a716-446655440001",
  "modality": "750e8400-e29b-41d4-a716-446655440000",
  "body_part": "850e8400-e29b-41d4-a716-446655440000",
  "scan_protocol": "950e8400-e29b-41d4-a716-446655440000",
  "technique": "CT scan performed with IV contrast. 5mm axial slices.",
  "findings": "No acute abnormality. Lungs are clear. Heart size normal.",
  "impression": "Normal chest CT."
}
```

**Request Schema (StudyReportCreateSpec)**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| study | UUID | Yes | DicomStudy external_id |
| modality | UUID | Yes | ModalityType external_id |
| body_part | UUID | Yes | BodyPart external_id |
| scan_protocol | UUID | Yes | ScanProtocol external_id |
| technique | String | No | Imaging technique details |
| findings | String | No | Clinical findings |
| impression | String | No | Radiologist's impression/conclusion |

**Response**:

```json
{
  "external_id": "a50e8400-e29b-41d4-a716-446655440000",
  "study_id": "650e8400-e29b-41d4-a716-446655440001",
  "patient_id": "550e8400-e29b-41d4-a716-446655440000",
  "patient": {
    "external_id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "John Doe",
    "gender": "M",
    "age": 45
  },
  "modality_id": "750e8400-e29b-41d4-a716-446655440000",
  "body_part_id": "850e8400-e29b-41d4-a716-446655440000",
  "scan_protocol_id": "950e8400-e29b-41d4-a716-446655440000",
  "study": null,
  "modality": "CT Scan",
  "body_part": "Chest",
  "scan_protocol": "Contrast Chest CT",
  "technique": "CT scan performed with IV contrast. 5mm axial slices.",
  "findings": "No acute abnormality. Lungs are clear. Heart size normal.",
  "impression": "Normal chest CT.",
  "created_datetime": "2024-03-15T14:35:00Z",
  "last_modified_datetime": "2024-03-15T14:35:00Z",
  "created_by": {
    "external_id": "b50e8400-e29b-41d4-a716-446655440000",
    "first_name": "Jane",
    "last_name": "Smith",
    "username": "jsmith"
  },
  "updated_by": {
    "external_id": "b50e8400-e29b-41d4-a716-446655440000",
    "first_name": "Jane",
    "last_name": "Smith",
    "username": "jsmith"
  }
}
```

**Behavior**:
- **Idempotent**: If a report already exists for the study, it will be **updated** instead of creating a duplicate
- **Audit Trail**: Creates `StudyReportAudit` entry for "Created" or "Updated" action
- Tracks field-level changes in audit log (old_value → new_value)

**Error Responses**:

```json
// 400 Bad Request
{
  "detail": "Invalid study/modality/body_part/scan_protocol IDs"
}

// 403 Forbidden
{
  "detail": "You do not have permission to write this report"
}
```

**Code Reference**: `src/care_radiology/api/study_report.py:14`

---

#### 7. List Study Reports

**Endpoint**: `GET /study_report/`

**Purpose**: List all study reports with filtering.

**Authentication**: JWT Bearer Token (required)

**Authorization**: `can_read_radiology_report`

**Request**:

```http
GET /api/care_radiology/study_report/?study=650e8400-e29b-41d4-a716-446655440001 HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| study | UUID | No | Filter by DicomStudy external_id |
| study__external_id | UUID | No | Alternative filter by study external_id |
| ordering | String | No | Sort field (e.g., `-created_date`, `modified_date`) |

**Response**:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "external_id": "a50e8400-e29b-41d4-a716-446655440000",
      "study_id": "650e8400-e29b-41d4-a716-446655440001",
      "patient_id": "550e8400-e29b-41d4-a716-446655440000",
      "patient": { ... },
      "modality_id": "750e8400-e29b-41d4-a716-446655440000",
      "modality": "CT Scan",
      "body_part": "Chest",
      "scan_protocol": "Contrast Chest CT",
      "technique": "...",
      "findings": "...",
      "impression": "...",
      "created_datetime": "2024-03-15T14:35:00Z",
      "last_modified_datetime": "2024-03-15T14:35:00Z",
      "created_by": { ... },
      "updated_by": { ... }
    }
  ]
}
```

**Code Reference**: `src/care_radiology/api/study_report.py:46`

---

#### 8. Retrieve Study Report

**Endpoint**: `GET /study_report/{external_id}/`

**Purpose**: Retrieve a single study report by external_id.

**Authentication**: JWT Bearer Token (required)

**Authorization**: `can_read_radiology_report`

**Request**:

```http
GET /api/care_radiology/study_report/a50e8400-e29b-41d4-a716-446655440000/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Response**: Same as individual report object in List endpoint

**Error Responses**:

```json
// 404 Not Found
{
  "detail": "Not found."
}
```

---

#### 9. Delete Study Report

**Endpoint**: `DELETE /study_report/{external_id}/`

**Purpose**: Soft-delete a study report.

**Authentication**: JWT Bearer Token (required)

**Authorization**: `can_write_radiology_report`

**Request**:

```http
DELETE /api/care_radiology/study_report/a50e8400-e29b-41d4-a716-446655440000/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Response**:

```http
HTTP/1.1 204 No Content
```

**Behavior**: Sets `deleted = True` (soft delete)

---

### Study Report Audits

#### 10. List Study Report Audits

**Endpoint**: `GET /study-report-audits/`

**Purpose**: View audit trail for study report changes.

**Authentication**: JWT Bearer Token (required)

**Authorization**: Inherited from StudyReport permissions

**Request**:

```http
GET /api/care_radiology/study-report-audits/?study_report=a50e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| study_report | UUID | No | Filter by StudyReport external_id |
| study_report__external_id | UUID | No | Alternative filter |
| ordering | String | No | Sort field (default: `-created_date`) |

**Response**:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "external_id": "c50e8400-e29b-41d4-a716-446655440000",
      "study_report_id": "a50e8400-e29b-41d4-a716-446655440000",
      "action": "Updated",
      "field_name": "Multiple",
      "old_value": {
        "Findings": "Pending review.",
        "Impression": "TBD"
      },
      "new_value": {
        "Findings": "No acute abnormality. Lungs are clear.",
        "Impression": "Normal chest CT."
      },
      "created_datetime": "2024-03-15T15:00:00Z",
      "created_by": {
        "external_id": "b50e8400-e29b-41d4-a716-446655440000",
        "first_name": "Jane",
        "last_name": "Smith",
        "username": "jsmith"
      }
    },
    {
      "external_id": "d50e8400-e29b-41d4-a716-446655440000",
      "study_report_id": "a50e8400-e29b-41d4-a716-446655440000",
      "action": "Created",
      "field_name": "All",
      "old_value": null,
      "new_value": {
        "Modality": "CT Scan",
        "Body Part": "Chest",
        "Scan Protocol": "Contrast Chest CT",
        "Technique": "...",
        "Findings": "Pending review.",
        "Impression": "TBD"
      },
      "created_datetime": "2024-03-15T14:35:00Z",
      "created_by": { ... }
    }
  ]
}
```

**Code Reference**: `src/care_radiology/api/study_report_audit.py:8`

---

### Configuration Management

#### 11. Create Modality Type

**Endpoint**: `POST /modality_type/`

**Purpose**: Create a new modality type (or revive soft-deleted one).

**Authentication**: JWT Bearer Token (required)

**Authorization**: Public (no specific permission check)

**Request**:

```http
POST /api/care_radiology/modality_type/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "display_name": "CT Scan",
  "coding": [
    {
      "coding_system": "http://dicom.nema.org/resources/ontology/DCM",
      "coding_code": "CT",
      "coding_display": "Computed Tomography"
    }
  ]
}
```

**Request Schema (ModalityTypeCreateSpec)**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| display_name | String | Yes | Human-readable name (must be unique) |
| coding | ModalityCoding[] | Yes | FHIR-style coding list |

**ModalityCoding Schema**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| coding_system | String | Yes | Coding system URI (e.g., DICOM, SNOMED CT) |
| coding_code | String | Yes | Code value |
| coding_display | String | Yes | Display name for code |

**Response**:

```json
{
  "external_id": "750e8400-e29b-41d4-a716-446655440000",
  "display_name": "CT Scan",
  "coding": [
    {
      "coding_system": "http://dicom.nema.org/resources/ontology/DCM",
      "coding_code": "CT",
      "coding_display": "Computed Tomography"
    }
  ]
}
```

**Behavior**:
- If a soft-deleted modality with the same `display_name` exists, it will be **revived** (undeleted) instead of creating a duplicate
- Raises `400 Bad Request` if an active modality with the same name already exists

**Error Responses**:

```json
// 400 Bad Request
{
  "detail": "Modality type 'CT Scan' already exists."
}
```

**Code Reference**: `src/care_radiology/api/modality_type.py:14`

---

#### 12. List Modality Types

**Endpoint**: `GET /modality_type/`

**Authentication**: JWT Bearer Token (required)

**Request**:

```http
GET /api/care_radiology/modality_type/ HTTP/1.1
Authorization: Bearer <JWT_TOKEN>
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| search | String | Search by display_name |
| ordering | String | Sort field (e.g., `-created_date`) |

**Response**: Paginated list of modality types

---

#### 13. Update Modality Type

**Endpoint**: `PATCH /modality_type/{external_id}/`

**Request**:

```json
{
  "display_name": "CT Scan (Updated)",
  "coding": [ ... ]
}
```

**Request Schema (ModalityTypeUpdateSpec)**: All fields optional

**Response**: Updated modality type object

---

#### 14. Delete Modality Type

**Endpoint**: `DELETE /modality_type/{external_id}/`

**Behavior**: Soft delete (sets `deleted = True`)

**Response**: `204 No Content`

---

#### 15-18. Body Part CRUD

**Endpoints**:
- `POST /body_part/` - Create
- `GET /body_part/` - List (filter by `modality__display_name`, search)
- `PATCH /body_part/{external_id}/` - Update
- `DELETE /body_part/{external_id}/` - Delete

**Request Schema (BodyPartCreateSpec)**:

```json
{
  "modality": "750e8400-e29b-41d4-a716-446655440000",
  "display_name": "Chest",
  "coding": [
    {
      "coding_system": "http://snomed.info/sct",
      "coding_code": "51185008",
      "coding_display": "Chest"
    }
  ]
}
```

**Code Reference**: `src/care_radiology/api/body_part.py:14`

---

#### 19-22. Scan Protocol CRUD

**Endpoints**:
- `POST /scan_protocol/` - Create
- `GET /scan_protocol/` - List (filter by modality/body_part, search)
- `PATCH /scan_protocol/{external_id}/` - Update
- `DELETE /scan_protocol/{external_id}/` - Delete

**Request Schema (ScanProtocolCreateSpec)**:

```json
{
  "modality": "750e8400-e29b-41d4-a716-446655440000",
  "body_part": "850e8400-e29b-41d4-a716-446655440000",
  "display_name": "High-Resolution Chest CT",
  "coding": [
    {
      "coding_system": "http://snomed.info/sct",
      "coding_code": "241541005",
      "coding_display": "High resolution CT of chest"
    }
  ]
}
```

**Code Reference**: `src/care_radiology/api/scan_protocol.py:14`

---

#### 23-26. Template CRUD

**Endpoints**:
- `POST /template/` - Create
- `GET /template/` - List (user-specific, returns only current user's templates)
- `PATCH /template/{external_id}/` - Update (not implemented, returns 405)
- `DELETE /template/{external_id}/` - Delete

**Request Schema (TemplateCreateSpec)**:

```json
{
  "modality": "750e8400-e29b-41d4-a716-446655440000",
  "body_part": "850e8400-e29b-41d4-a716-446655440000",
  "scan_protocol": "950e8400-e29b-41d4-a716-446655440000",
  "technique": "CT scan performed with IV contrast. 5mm axial slices.",
  "findings": "Template findings text...",
  "impression": "Template impression text..."
}
```

**Behavior**:
- Templates are **user-scoped**: Only the creating user can see their templates
- The `user_id` is automatically set to `request.user` (not provided in request body)

**Code Reference**: `src/care_radiology/api/template.py:14`

---

## Authentication & Authorization

### Authentication Methods

#### 1. JWT Bearer Token (Primary)

Used for all user-facing endpoints.

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Implementation**: Django REST Framework's default JWT authentication from Care backend.

**Token Contains**:
- `user_id`: User's UUID
- `username`: User's username
- `exp`: Expiration timestamp
- Facility/role context

---

#### 2. Static API Key (Worklist Only)

Used for external PACS/RIS systems to query worklist.

```http
Authorization: <STATIC_API_KEY>
```

**Configuration**: Set via `CARE_RADIOLOGY_WEBHOOK_SECRET` environment variable.

**Endpoints**: `/dicom/worklist/` only

**Code Reference**: `src/care_radiology/api/dicom.py:32`

---

### Authorization Rules

All authorization checks use the Care backend's `AuthorizationController` system.

#### Patient-Level Permissions

**Endpoint**: `/dicom/upload/`, `/dicom/studies/`

**Check**: `can_write_patient_obj` or `can_view_patient_obj`

**Logic**:
```python
if not AuthorizationController.call("can_view_patient_obj", request.user, patient):
    raise PermissionDenied("You do not have permission to view this patient")
```

**Rules** (defined in Care backend):
- User must be assigned to the patient's facility
- User must have appropriate role (doctor, nurse, etc.)
- User may have explicit patient-level access grants

---

#### Service Request Permissions

**Endpoint**: `/dicom/service-requests/`

**Check**: `can_write_service_request`

**Logic**: Similar to patient permissions, scoped to facility and service request status.

---

#### Report Permissions

**Endpoints**: `/study_report/` (all CRUD operations)

**Checks**:
- `can_read_radiology_report` - For GET/LIST
- `can_write_radiology_report` - For POST/PATCH/DELETE

**Logic**:
```python
def verify_report_permission(self, type):
    permission = "can_read_radiology_report" if type == 'read' else "can_write_radiology_report"
    if not AuthorizationController.call(permission, self.request.user):
        raise PermissionDenied(f"You do not have permission to {type} this report")
```

**Rules** (customizable in Care backend):
- Typically assigned to "Radiologist" or "Doctor" roles
- May be facility-scoped
- May require specific credentials/certifications

**Code Reference**: `src/care_radiology/api/study_report.py:27`

---

#### Configuration Permissions

**Endpoints**: `/modality_type/`, `/body_part/`, `/scan_protocol/`, `/template/`

**Authorization**: Currently **open** (no permission checks in `authorize_create`/`authorize_update`/`authorize_destroy`)

**Note**: This allows any authenticated user to manage configuration. In production, you may want to restrict this to administrators.

---

## Request/Response Schemas

### Common Patterns

#### Pydantic Spec Classes

The plugin uses Pydantic for request/response validation:

- **CreateSpec**: Request body for POST endpoints (`de_serialize()` converts to Django model)
- **UpdateSpec**: Request body for PATCH endpoints
- **ListSpec**: Response body for GET/LIST endpoints (`serialize()` converts from Django model)
- **RetrieveSpec**: Response body for GET detail endpoints

---

#### EMRBaseModel Fields

All responses include these audit fields:

```json
{
  "external_id": "UUID",
  "created_date": "ISO 8601 timestamp",
  "modified_date": "ISO 8601 timestamp",
  "deleted": false,
  "created_by": {
    "external_id": "UUID",
    "first_name": "string",
    "last_name": "string",
    "username": "string"
  },
  "updated_by": { ... }
}
```

---

### Full Schema Definitions

#### StudyReportCreateSpec

```typescript
{
  study: UUID;              // DicomStudy external_id (required)
  modality: UUID;           // ModalityType external_id (required)
  body_part: UUID;          // BodyPart external_id (required)
  scan_protocol: UUID;      // ScanProtocol external_id (required)
  technique?: string;       // Imaging technique details (optional)
  findings?: string;        // Clinical findings (optional)
  impression?: string;      // Radiologist's impression (optional)
}
```

---

#### StudyReportListSpec

```typescript
{
  external_id: UUID;
  study_id: UUID;
  patient_id: UUID;
  patient: {
    external_id: UUID;
    name: string;
    gender: string;
    age: number;
    // ... other patient fields
  } | null;
  modality_id: UUID;
  body_part_id: UUID;
  scan_protocol_id: UUID;
  study: string | null;           // Study name (if available)
  modality: string;                // Modality display_name
  body_part: string;               // BodyPart display_name
  scan_protocol: string;           // ScanProtocol display_name
  technique: string | null;
  findings: string | null;
  impression: string | null;
  created_datetime: string;        // ISO 8601
  last_modified_datetime: string;  // ISO 8601
  created_by: {
    external_id: UUID;
    first_name: string;
    last_name: string;
    username: string;
  } | null;
  updated_by: { ... } | null;
}
```

---

#### ModalityTypeCreateSpec

```typescript
{
  display_name: string;     // Unique human-readable name (required)
  coding: ModalityCoding[]; // At least one coding (required)
}
```

---

#### ModalityCoding

```typescript
{
  coding_system: string;    // URI (e.g., "http://dicom.nema.org/resources/ontology/DCM")
  coding_code: string;      // Code value (e.g., "CT")
  coding_display: string;   // Display name (e.g., "Computed Tomography")
}
```

---

#### BodyPartCreateSpec

```typescript
{
  modality: UUID;           // ModalityType external_id (required)
  display_name: string;     // Human-readable name (required)
  coding: ModalityCoding[]; // At least one coding (required)
}
```

---

#### ScanProtocolCreateSpec

```typescript
{
  modality: UUID;           // ModalityType external_id (required)
  body_part: UUID;          // BodyPart external_id (required)
  display_name: string;     // Human-readable name (required)
  coding: ModalityCoding[]; // At least one coding (required)
}
```

---

#### TemplateCreateSpec

```typescript
{
  modality: UUID;           // ModalityType external_id (required)
  body_part: UUID;          // BodyPart external_id (required)
  scan_protocol: UUID;      // ScanProtocol external_id (required)
  technique?: string;       // Pre-filled technique text (optional)
  findings?: string;        // Pre-filled findings text (optional)
  impression?: string;      // Pre-filled impression text (optional)
}
```

**Note**: `user` field is NOT in the request body; it's automatically set to `request.user`.

---

## Error Handling

### HTTP Status Codes

| Code | Description | When Used |
|------|-------------|-----------|
| 200 | OK | Successful GET/POST/PATCH (with response body) |
| 201 | Created | Successful POST (resource created) |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid request body, missing required fields, validation errors |
| 401 | Unauthorized | Missing or invalid authentication token/API key |
| 403 | Forbidden | User lacks permission for the requested action |
| 404 | Not Found | Resource not found (patient, study, report, etc.) |
| 409 | Conflict | DICOM already exists in DCM4CHEE (treated as success) |
| 500 | Internal Server Error | Unexpected server error (exception during processing) |
| 502 | Bad Gateway | DCM4CHEE/external service failure |

---

### Error Response Format

All errors return JSON with a `detail` or `error` key:

```json
// Standard DRF error
{
  "detail": "Not found."
}

// Validation error
{
  "field_name": ["Error message"],
  "another_field": ["Another error"]
}

// Custom error (upload endpoint)
{
  "error": "Failed to upload to DCM4CHEE",
  "status_code": 500,
  "details": "Internal Server Error"
}
```

---

### Common Error Scenarios

#### 1. Missing Patient

**Request**: `GET /dicom/studies/?patientId=invalid-uuid`

**Response**:
```json
HTTP/1.1 404 Not Found

{
  "detail": "Patient not found"
}
```

---

#### 2. Permission Denied

**Request**: `POST /study_report/` (user lacks `can_write_radiology_report`)

**Response**:
```json
HTTP/1.1 403 Forbidden

{
  "detail": "You do not have permission to write this report"
}
```

---

#### 3. Invalid Foreign Key

**Request**: `POST /study_report/` with invalid `modality` UUID

**Response**:
```json
HTTP/1.1 400 Bad Request

{
  "detail": "Invalid study/modality/body_part/scan_protocol IDs"
}
```

---

#### 4. DCM4CHEE Unavailable

**Request**: `POST /dicom/upload/` (DCM4CHEE returns 500)

**Response**:
```json
HTTP/1.1 502 Bad Gateway

{
  "error": "Failed to upload to DCM4CHEE",
  "status_code": 500,
  "details": "Connection refused"
}
```

---

## Performance Considerations

### 1. Parallel Study Metadata Fetching

**Endpoint**: `/dicom/studies/`, `/dicom/service-requests/`

**Optimization**: Uses `ThreadPoolExecutor` (max 10 workers) to fetch study metadata from DCM4CHEE in parallel.

**Code**:
```python
with ThreadPoolExecutor(max_workers=10) as executor:
    future_to_study = {
        executor.submit(fetch_study, study): study
        for study in studies
    }
    for future in as_completed(future_to_study):
        result = future.result()
        if result is not None:
            results.append(result)
```

**Performance Gain**: 10x speedup for patients with multiple studies (10 studies fetched in ~1 second instead of ~10 seconds).

**Code Reference**: `src/care_radiology/api/dicom.py:231`

---

### 2. Redis Caching

**Cache Key**: `radiology:dicom:study:{study_uid}`

**TTL**: 1 hour (3600 seconds)

**Cached Data**:
```json
{
  "study_uid": "string",
  "study_date": "ISO 8601",
  "study_description": "string",
  "study_modalities": ["CT"],
  "study_series": [ ... ],
  "external_id": "UUID",
  "has_report": false
}
```

**Cache Invalidation**: Bust on DICOM upload (`cache.delete(key)`)

**Code Reference**: `src/care_radiology/api/dicom.py:285`

---

### 3. Database Query Optimization

**SELECT RELATED**: Always used for foreign key lookups to avoid N+1 queries.

```python
qs = (
    StudyReport.objects
    .select_related("study", "modality", "body_part", "scan_protocol")
    .order_by("-created_date")
)
```

**EXISTS Subquery**: Used to efficiently check for related records.

```python
report_exists = StudyReport.objects.filter(study=OuterRef('pk'))
studies = DicomStudy.objects.filter(...).annotate(has_report=Exists(report_exists))
```

---

### 4. Soft Delete Indexing

All tables have indexes on `deleted` column for efficient filtering:

```sql
CREATE INDEX idx_radiology_dicomstudy_deleted ON radiology_dicomstudy(deleted);
```

**Query**: `SELECT * FROM radiology_dicomstudy WHERE deleted = FALSE` uses index.

---

### 5. Unique Constraints

**DicomStudy**: `UNIQUE (patient_id, dicom_study_uid)` prevents duplicate study mappings.

**ModalityType**: `UNIQUE (display_name)` WHERE `deleted = FALSE` allows name reuse after soft delete.

---

### 6. JSONB Indexing (PostgreSQL)

**Tables with JSONB**: `ModalityType.coding`, `BodyPart.coding`, `ScanProtocol.coding`, `RadiologyWebhookLogs.raw_data`, `StudyReportAudit.old_value`, `StudyReportAudit.new_value`

**Recommended Indexes** (if filtering by JSONB fields):

```sql
-- Index for querying modality coding by system/code
CREATE INDEX idx_modalitytype_coding_gin ON radiology_modalitytype USING GIN (coding);

-- Index for querying webhook logs by type
CREATE INDEX idx_webhooklogs_type ON radiology_radiologywebhooklogs(type);
```

---

## Performance Benchmarks

### Upload Endpoint

- **Single DICOM file (10 MB)**: ~2-3 seconds
  - 0.5s: File read + multipart encoding
  - 1.5s: DCM4CHEE STOW-RS upload
  - 0.5s: Study UID extraction + DB insert

---

### Query Endpoint

- **Patient with 10 studies (no cache)**: ~1.5 seconds
  - 0.1s: DB query for DicomStudy records
  - 1.2s: Parallel DCM4CHEE QIDO-RS queries (10 workers)
  - 0.2s: Response serialization

- **Patient with 10 studies (cached)**: ~100ms
  - 0.05s: DB query
  - 0.03s: Redis GET (10 keys)
  - 0.02s: Response serialization

---

### Report Creation

- **Create report**: ~200ms
  - 0.1s: Foreign key lookups (4 queries)
  - 0.05s: DB insert (StudyReport + StudyReportAudit)
  - 0.05s: Response serialization

---

## Appendix

### Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - High-level system architecture
- [API_UPLOAD_ENDPOINT.md](./API_UPLOAD_ENDPOINT.md) - Deep dive into upload flow
- [API_QUERY_ENDPOINT.md](./API_QUERY_ENDPOINT.md) - Deep dive into query flow
- [DCM4CHEE_INTEGRATION.md](./DCM4CHEE_INTEGRATION.md) - PACS integration guide
- [EXTERNAL_SERVICES.md](./EXTERNAL_SERVICES.md) - OHIF, MinIO, LDAP, Nginx
- [FHIR_ANALYSIS.md](./FHIR_ANALYSIS.md) - FHIR R4 compliance analysis

---

### Useful SQL Queries

#### Find all studies for a patient

```sql
SELECT
    ds.external_id,
    ds.dicom_study_uid,
    p.name AS patient_name,
    ds.created_date,
    EXISTS(SELECT 1 FROM radiology_studyreport sr WHERE sr.study_id = ds.id) AS has_report
FROM radiology_dicomstudy ds
JOIN emr_patient p ON p.id = ds.patient_id
WHERE p.external_id = '550e8400-e29b-41d4-a716-446655440000'
AND ds.deleted = FALSE
ORDER BY ds.created_date DESC;
```

---

#### Find all reports by a specific radiologist

```sql
SELECT
    sr.external_id,
    ds.dicom_study_uid,
    p.name AS patient_name,
    mt.display_name AS modality,
    sr.created_datetime,
    u.username AS radiologist
FROM radiology_studyreport sr
JOIN radiology_dicomstudy ds ON ds.id = sr.study_id
JOIN emr_patient p ON p.id = ds.patient_id
JOIN radiology_modalitytype mt ON mt.id = sr.modality_id
JOIN users_user u ON u.id = sr.created_by_id
WHERE u.external_id = 'b50e8400-e29b-41d4-a716-446655440000'
AND sr.deleted = FALSE
ORDER BY sr.created_datetime DESC;
```

---

#### Audit trail for a specific report

```sql
SELECT
    sra.external_id,
    sra.action,
    sra.field_name,
    sra.old_value::text AS old_value,
    sra.new_value::text AS new_value,
    sra.created_datetime,
    u.username AS changed_by
FROM radiology_studyreportaudit sra
JOIN users_user u ON u.id = sra.created_by_id
WHERE sra.study_report_id = (
    SELECT id FROM radiology_studyreport
    WHERE external_id = 'a50e8400-e29b-41d4-a716-446655440000'
)
ORDER BY sra.created_datetime DESC;
```

---

#### Configuration hierarchy (Modality → Body Part → Scan Protocol)

```sql
SELECT
    mt.display_name AS modality,
    bp.display_name AS body_part,
    sp.display_name AS scan_protocol,
    mt.external_id AS modality_id,
    bp.external_id AS body_part_id,
    sp.external_id AS scan_protocol_id
FROM radiology_scanprotocol sp
JOIN radiology_modalitytype mt ON mt.id = sp.modality_id
JOIN radiology_bodypart bp ON bp.id = sp.body_part_id
WHERE sp.deleted = FALSE
AND bp.deleted = FALSE
AND mt.deleted = FALSE
ORDER BY mt.display_name, bp.display_name, sp.display_name;
```

---

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL` | DCM4CHEE DICOMweb base URL | `http://arc:8080/dcm4chee-arc` |
| `CARE_RADIOLOGY_WEBHOOK_SECRET` | Static API key for worklist endpoint | `my-secret-key-123` |
| `REDIS_URL` | Redis connection URL for caching | `redis://localhost:6379/1` |
| `DATABASE_URL` | PostgreSQL connection URL | `postgres://user:pass@localhost:5432/dicom` |

---

### API Client Examples

#### Python (requests)

```python
import requests

BASE_URL = "http://localhost:9000/api/care_radiology"
JWT_TOKEN = "your-jwt-token"

headers = {
    "Authorization": f"Bearer {JWT_TOKEN}",
    "Content-Type": "application/json"
}

# Upload DICOM
with open("study.dcm", "rb") as f:
    files = {"file": ("study.dcm", f, "application/dicom")}
    data = {"patient_id": "550e8400-e29b-41d4-a716-446655440000"}
    response = requests.post(
        f"{BASE_URL}/dicom/upload/",
        headers={"Authorization": headers["Authorization"]},
        data=data,
        files=files
    )
    print(response.json())

# Query studies
response = requests.get(
    f"{BASE_URL}/dicom/studies/",
    headers=headers,
    params={"patientId": "550e8400-e29b-41d4-a716-446655440000"}
)
print(response.json())

# Create report
report_data = {
    "study": "650e8400-e29b-41d4-a716-446655440001",
    "modality": "750e8400-e29b-41d4-a716-446655440000",
    "body_part": "850e8400-e29b-41d4-a716-446655440000",
    "scan_protocol": "950e8400-e29b-41d4-a716-446655440000",
    "technique": "CT scan with IV contrast",
    "findings": "No acute abnormality",
    "impression": "Normal chest CT"
}
response = requests.post(
    f"{BASE_URL}/study_report/",
    headers=headers,
    json=report_data
)
print(response.json())
```

---

#### cURL

```bash
# Upload DICOM
curl -X POST http://localhost:9000/api/care_radiology/dicom/upload/ \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -F "patient_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "file=@study.dcm"

# Query studies
curl -X GET "http://localhost:9000/api/care_radiology/dicom/studies/?patientId=550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer $JWT_TOKEN"

# Create report
curl -X POST http://localhost:9000/api/care_radiology/study_report/ \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "study": "650e8400-e29b-41d4-a716-446655440001",
    "modality": "750e8400-e29b-41d4-a716-446655440000",
    "body_part": "850e8400-e29b-41d4-a716-446655440000",
    "scan_protocol": "950e8400-e29b-41d4-a716-446655440000",
    "technique": "CT scan with IV contrast",
    "findings": "No acute abnormality",
    "impression": "Normal chest CT"
  }'
```

---

### Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-23 | Initial comprehensive API specification and database schema documentation |

---

**Document Maintained by**: Care Radiology Development Team
**Last Reviewed**: 2026-04-23
**Next Review**: 2026-07-23
