# Care Radiology Plugin - Architecture Documentation

## Document Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-04-22 | **Major Update**: Added comprehensive reporting system documentation including StudyReport, StudyReportAudit, ModalityType, BodyPart, ScanProtocol, Template models; new API endpoints for reporting; worklist functionality; updated authentication and authorization; complete reports workflow documentation |
| 1.0 | 2025-04-16 | Initial comprehensive architecture documentation |

## Latest Updates (v2.0)

**New Features**:
- ✅ **Radiology Reporting System**: Complete CRUD for structured reports with technique/findings/impression
- ✅ **Audit Trail**: Automatic change tracking for all report modifications (HIPAA compliance)
- ✅ **Configuration Management**: Hierarchical modality → body part → scan protocol setup
- ✅ **Template System**: User-specific report templates for faster report generation
- ✅ **Worklist API**: Query pending radiology service requests with filtering
- ✅ **Report Status Tracking**: `has_report` annotation on DICOM studies
- ✅ **Enhanced Permissions**: Fine-grained `can_read_radiology_report` and `can_write_radiology_report`
- ✅ **Static API Key Auth**: For webhooks and worklist endpoints

**New Models**:
- StudyReport, StudyReportAudit, ModalityType, BodyPart, ScanProtocol, Template

**New API Endpoints**:
- `/dicom/worklist/`, `/study_report/`, `/study-report-audits/`, `/modality_type/`, `/body_part/`, `/scan_protocol/`, `/template/`

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Technology Stack](#technology-stack)
4. [Database Models](#database-models)
   - DicomStudy, RadiologyServiceRequest, RadiologyWebhookLogs
   - **NEW**: StudyReport, StudyReportAudit
   - **NEW**: ModalityType, BodyPart, ScanProtocol, Template
5. [API Endpoints](#api-endpoints)
   - DICOM Operations (upload, studies, service-requests, worklist)
   - **NEW**: Reporting (study_report, study-report-audits)
   - **NEW**: Configuration (modality_type, body_part, scan_protocol, template)
   - Webhooks
6. [Service Integrations](#service-integrations)
7. [**NEW**: Reports Workflow](#reports-workflow)
   - Report Creation Workflow
   - Report Status Tracking
   - Template Workflow
   - Compliance Features
8. [DICOM Workflows](#dicom-workflows)
9. [Authentication & Authorization](#authentication--authorization)
   - **NEW**: Report Permissions
10. [Docker Infrastructure](#docker-infrastructure)
11. [Configuration](#configuration)
12. [Deployment Guide](#deployment-guide)

---

## Overview

The **Care Radiology Plugin** is a Django plugin that extends the CARE EMR system with comprehensive DICOM (Digital Imaging and Communications in Medicine) capabilities. It provides a complete radiology workflow solution by integrating with industry-standard PACS (Picture Archiving and Communication System) infrastructure.

### Key Features

- **DICOM Upload & Storage**: Upload medical images to DCM4CHEE archive
- **Study Management**: Query and retrieve DICOM studies linked to patients
- **Radiology Reporting**: Complete reporting system with templates, findings, and impressions
- **Report Audit Trail**: Track all changes to radiology reports with full history
- **Web Viewer Integration**: OHIF-based web viewer for DICOM images
- **Worklist Management**: Query and filter radiology service requests for workflow optimization
- **Webhook Support**: Event-driven integration with external systems
- **Authorization**: Fine-grained patient, service request, and report level access control
- **Configuration Management**: Modality types, body parts, and scan protocols for standardized reporting
- **Template System**: User-specific report templates for faster report generation
- **Compliance**: Complete audit trail for all webhook events and report modifications

### Core Value Proposition

The plugin acts as a **metadata bridge** between CARE's clinical workflow system and a complete radiology PACS stack, without storing actual DICOM images in CARE's database. This design:
- Keeps CARE lightweight and focused on clinical workflows
- Delegates image storage and DICOM compliance to specialized systems (DCM4CHEE)
- Maintains patient-study relationships for clinical context
- Provides seamless integration with existing CARE authorization models

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CARE Frontend (React)                           │
│  - Patient Management                                                     │
│  - Service Request Workflow                                               │
│  - Radiology Order Entry                                                  │
└──────────────┬──────────────────────────────────────────────┬─────────────┘
               │                                               │
               │ REST API                                      │ Direct Access
               │                                               │
┌──────────────▼───────────────────────────────┐  ┌───────────▼─────────────┐
│     CARE Backend (Django)                    │  │   OHIF Viewer           │
│  ┌────────────────────────────────────────┐  │  │   (Port 3000)           │
│  │  care_radiology Plugin                 │  │  └─────────────────────────┘
│  │                                        │  │               │
│  │  API Endpoints:                        │  │               │
│  │  - POST /dicom/upload/                 │  │               │
│  │  - GET  /dicom/studies/                │  │               │
│  │  - GET  /dicom/service-requests/       │  │               │
│  │  - GET  /dicom/worklist/               │  │               │
│  │  - POST /dicom/authenticate/           │  │               │
│  │  - POST /webhooks/study/               │  │               │
│  │  - CRUD /study_report/                 │  │               │
│  │  - GET  /study-report-audits/          │  │               │
│  │  - CRUD /modality_type/                │  │               │
│  │  - CRUD /body_part/                    │  │               │
│  │  - CRUD /scan_protocol/                │  │               │
│  │  - CRUD /template/                     │  │               │
│  │                                        │  │               │
│  │  Models:                               │  │               │
│  │  - DicomStudy                          │  │               │
│  │  - RadiologyServiceRequest             │  │               │
│  │  - RadiologyWebhookLogs                │  │               │
│  │  - StudyReport                         │  │               │
│  │  - StudyReportAudit                    │  │               │
│  │  - ModalityType, BodyPart              │  │               │
│  │  - ScanProtocol, Template              │  │               │
│  └────────────┬───────────────────────────┘  │               │
│               │                               │               │
│  ┌────────────▼───────────────────────────┐  │               │
│  │  CARE Models                           │  │               │
│  │  - Patient                             │  │               │
│  │  - ServiceRequest                      │  │               │
│  │  - User & Authorization                │  │               │
│  └────────────────────────────────────────┘  │               │
└──────────────┬───────────────────────────────┘               │
               │                                               │
               │ HTTP (DICOMweb)                              │ HTTP
               │                                               │
┌──────────────▼───────────────────────────────────────────────▼─────────────┐
│                    Nginx Reverse Proxy (Port 32314)                        │
│                                                                             │
│  Routes:                                                                    │
│  - / → OHIF Viewer                                                         │
│  - /dicomweb/* → DCM4CHEE (with auth_request check)                       │
│  - /authenticate → CARE Backend (internal subrequest)                      │
│                                                                             │
│  Authentication Flow:                                                       │
│    Browser Request → auth_request → CARE verify JWT → proxy to DCM4CHEE   │
└──────────────┬────────────────────────────────────────────────────────────┘
               │
               │ DICOMweb (QIDO/WADO/STOW)
               │
┌──────────────▼─────────────────────────────────────────────────────────────┐
│                      DCM4CHEE Archive (Port 8080)                          │
│                                                                             │
│  - DICOM Storage (STOW-RS)                                                 │
│  - Query/Retrieve (QIDO-RS, WADO-RS)                                       │
│  - Metadata Management                                                      │
│  - Study/Series/Instance Registry                                          │
└──────────────┬───────────────┬─────────────────────────────────────────────┘
               │               │
       ┌───────▼──────┐  ┌────▼────────┐
       │  PostgreSQL   │  │   LDAP      │
       │  (Port 5432)  │  │ (Port 3890) │
       │               │  │             │
       │  - dicom DB   │  │  - Config   │
       └───────────────┘  │  - Storage  │
                          └─────────────┘
                                 │
                          ┌──────▼──────┐
                          │    MinIO    │
                          │  (S3 API)   │
                          │             │
                          │ dicom-bucket│
                          └─────────────┘
```

---

## Technology Stack

### Backend

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Web Framework** | Django | 6.0+ | Application framework |
| **REST API** | Django REST Framework | Latest | API endpoints |
| **Task Queue** | Celery | Latest | Async task processing |
| **Database** | PostgreSQL | 13+ | Primary data store |
| **Cache** | Redis | 6+ | Caching layer |

### DICOM Infrastructure

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **PACS** | DCM4CHEE Archive | 5.34.1 | DICOM storage & management |
| **Viewer** | OHIF | v3.9.2 | Web-based DICOM viewer |
| **Object Storage** | MinIO | Latest | Image file storage (S3-compatible) |
| **Directory** | OpenLDAP | 2.6.8 | DCM4CHEE configuration |
| **Reverse Proxy** | Nginx | Alpine | Routing & authentication |

### Python Dependencies

```python
django>=6.0
djangorestframework>=3.14
celery>=5.3
django-environ>=0.11
requests>=2.31
```

---

## Database Models

### DicomStudy

**Purpose**: Maps DICOM studies from DCM4CHEE to CARE patients.

**Table**: `radiology_dicomstudy`

```python
class DicomStudy(EMRBaseModel):
    patient = models.ForeignKey(
        "emr.Patient",
        on_delete=models.CASCADE,
        related_name="dicom_studies"
    )
    dicom_study_uid = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "dicom_study_uid"],
                name="unique_patient_study"
            )
        ]
```

**Fields**:
- `patient`: Foreign key to CARE Patient model
- `dicom_study_uid`: DICOM Study Instance UID (unique identifier from PACS)
- Plus inherited from `EMRBaseModel`:
  - `id`, `external_id`, `created_date`, `modified_date`
  - `created_by`, `updated_by`, `deleted`, `history`, `meta`

**Relationships**:
- One patient → Many DICOM studies
- One DICOM study → Many service requests (via RadiologyServiceRequest)

---

-- review comments i feel it should be encounter to dicom study 

### RadiologyServiceRequest

**Purpose**: Links CARE service requests to DICOM studies, bridging clinical workflow with radiology images.

**Table**: `radiology_servicerequest`

```python
class RadiologyServiceRequest(EMRBaseModel):
    service_request = models.ForeignKey(
        "emr.ServiceRequest",
        on_delete=models.CASCADE,
        null=True,
        related_name="radiology_service_requests"
    )
    dicom_study = models.ForeignKey(
        DicomStudy,
        on_delete=models.CASCADE,
        null=True,
        related_name="dicom_studies"
    )
    raw_data = models.JSONField()
```

**Fields**:
- `service_request`: Link to CARE's service request (radiology order)
- `dicom_study`: Link to DicomStudy (actual images)
- `raw_data`: JSON payload from webhook or upload metadata

**Use Cases**:
- Track which service requests have associated imaging
- Link multiple studies to a single order (e.g., follow-up scans)
- Store webhook metadata for audit trails

---

### RadiologyWebhookLogs

**Purpose**: Audit trail for all incoming webhook events.

**Table**: `radiology_webhook_logs`

```python
class RadiologyWebhookLogs(EMRBaseModel):
    raw_data = models.JSONField()
    type = models.CharField(max_length=50)
```

**Fields**:
- `raw_data`: Complete webhook payload (for debugging and compliance)
- `type`: Event type (e.g., "SR-STUDY-INSERT")

**Use Cases**:
- Audit log for compliance
- Debugging webhook integration issues
- Analytics on DICOM workflow events

---

### StudyReport

**Purpose**: Captures radiology findings and interpretations for DICOM studies.

**Table**: `radiology_studyreport`

```python
class StudyReport(EMRBaseModel):
    study = models.ForeignKey(
        DicomStudy,
        on_delete=models.CASCADE,
        related_name="study_reports"
    )
    modality = models.ForeignKey(
        "ModalityType",
        on_delete=models.CASCADE
    )
    body_part = models.ForeignKey(
        "BodyPart",
        on_delete=models.CASCADE
    )
    scan_protocol = models.ForeignKey(
        "ScanProtocol",
        on_delete=models.CASCADE
    )
    technique = models.TextField(blank=True, default="")
    findings = models.TextField(blank=True, default="")
    impression = models.TextField(blank=True, default="")
    created_datetime = models.DateTimeField(auto_now_add=True)
    last_modified_datetime = models.DateTimeField(auto_now=True)
```

**Fields**:
- `study`: Foreign key to DicomStudy (which study this report describes)
- `modality`: Imaging modality used (CT, MR, X-Ray, etc.)
- `body_part`: Anatomical region examined
- `scan_protocol`: Specific imaging protocol used
- `technique`: Description of imaging technique/parameters
- `findings`: Detailed radiological findings
- `impression`: Radiologist's interpretation and conclusions

**Relationships**:
- One DicomStudy → Multiple StudyReports (e.g., initial + follow-up reports)
- Multiple reports can reference the same modality/body part/protocol

**Authorization**:
- `can_read_radiology_report`: View reports
- `can_write_radiology_report`: Create/modify reports

---

### StudyReportAudit

**Purpose**: Complete audit trail for all changes to radiology reports.

**Table**: `radiology_studyreportaudit`

```python
class StudyReportAudit(EMRBaseModel):
    study_report = models.ForeignKey(
        StudyReport,
        on_delete=models.CASCADE,
        related_name="audits"
    )
    action = models.CharField(max_length=20)  # "CREATED", "UPDATED"
    field_name = models.CharField(max_length=100)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    created_datetime = models.DateTimeField(auto_now_add=True)
    last_modified_datetime = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_datetime"]
```

**Fields**:
- `study_report`: Which report was modified
- `action`: Type of change (CREATED or UPDATED)
- `field_name`: Which field changed (e.g., "findings", "impression")
- `old_value`: Previous value (JSON-encoded)
- `new_value`: New value (JSON-encoded)
- `created_datetime`: When the change occurred

**Use Cases**:
- HIPAA compliance (track all report modifications)
- Report versioning
- Conflict resolution
- Quality assurance review

**Auto-Generated**: Audit entries created automatically on report save

---

### ModalityType

**Purpose**: Standardized list of medical imaging modalities.

**Table**: `radiology_modalitytype`

```python
class ModalityType(EMRBaseModel):
    display_name = models.CharField(max_length=255, unique=True)
    coding = models.JSONField(default=list)  # [{coding_system, coding_code, coding_display}]
```

**Fields**:
- `display_name`: Human-readable name (e.g., "Computed Tomography", "Magnetic Resonance")
- `coding`: Standardized codes (SNOMED CT, LOINC, etc.)

**Examples**:
- CT (Computed Tomography)
- MR (Magnetic Resonance)
- CR (Computed Radiography)
- DX (Digital X-Ray)
- US (Ultrasound)
- NM (Nuclear Medicine)

**Relationships**:
- One modality → Many body parts
- One modality → Many scan protocols
- One modality → Many reports

---

### BodyPart

**Purpose**: Anatomical regions that can be imaged with specific modalities.

**Table**: `radiology_bodypart`

```python
class BodyPart(EMRBaseModel):
    modality = models.ForeignKey(
        ModalityType,
        on_delete=models.CASCADE,
        related_name="body_parts"
    )
    display_name = models.CharField(max_length=255)
    coding = models.JSONField(default=list)
```

**Fields**:
- `modality`: Which imaging modality this applies to
- `display_name`: Human-readable name (e.g., "Brain", "Chest", "Abdomen")
- `coding`: Standardized anatomy codes

**Examples**:
- CT → Brain, Chest, Abdomen, Pelvis
- MR → Brain, Spine, Knee, Shoulder
- CR → Chest (PA/Lateral), Hand, Foot

**Hierarchical Structure**:
```
ModalityType: CT
├── BodyPart: Brain
├── BodyPart: Chest
└── BodyPart: Abdomen
```

---

### ScanProtocol

**Purpose**: Specific imaging protocols for modality + body part combinations.

**Table**: `radiology_scanprotocol`

```python
class ScanProtocol(EMRBaseModel):
    modality = models.ForeignKey(
        ModalityType,
        on_delete=models.CASCADE,
        related_name="scan_protocols"
    )
    body_part = models.ForeignKey(
        BodyPart,
        on_delete=models.CASCADE,
        related_name="scan_protocols"
    )
    display_name = models.CharField(max_length=255)
    coding = models.JSONField(default=list)
```

**Fields**:
- `modality`: Imaging modality
- `body_part`: Anatomical region
- `display_name`: Protocol name (e.g., "CT Brain without Contrast", "MR Knee Routine")
- `coding`: Procedure codes (CPT, ICD-10-PCS)

**Examples**:
```
Modality: CT
Body Part: Brain
├── Protocol: CT Brain without Contrast
├── Protocol: CT Brain with Contrast
└── Protocol: CT Brain Angiography

Modality: MR
Body Part: Knee
├── Protocol: MR Knee Routine
├── Protocol: MR Knee with Contrast
└── Protocol: MR Knee Arthrography
```

**Hierarchical Structure**:
```
ModalityType
└── BodyPart
    └── ScanProtocol
```

---

### Template

**Purpose**: User-specific report templates for faster report generation.

**Table**: `radiology_template`

```python
class Template(EMRBaseModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="templates"
    )
    modality = models.ForeignKey(ModalityType, on_delete=models.CASCADE)
    body_part = models.ForeignKey(BodyPart, on_delete=models.CASCADE)
    scan_protocol = models.ForeignKey(ScanProtocol, on_delete=models.CASCADE)
    technique = models.TextField(blank=True, default="")
    findings = models.TextField(blank=True, default="")
    impression = models.TextField(blank=True, default="")
```

**Fields**: Same structure as StudyReport, plus `user` field

**Use Cases**:
- Radiologists save frequently used report templates
- Pre-fill common findings/impressions
- Speed up report generation
- Maintain consistency in reporting style

**Workflow**:
1. Radiologist creates template for common study types
2. When creating new report, select template
3. Template auto-fills technique/findings/impression
4. Radiologist edits as needed for specific case

---

## API Endpoints

### Base URL
```
/api/care_radiology/
```

### 1. Authentication Check

```http
GET /dicom/authenticate/
```

**Purpose**: JWT verification endpoint called by nginx proxy to validate users.

**Authentication**: None (public endpoint, used by nginx internally)

**Response**:
```json
200 OK
```

**Usage**:
```nginx
# In nginx.conf
location /dicomweb/ {
    auth_request /authenticate;  # Calls this endpoint
    proxy_pass http://arc:8080;
}
```

---

### 2. DICOM Upload

```http
POST /dicom/upload/
Content-Type: multipart/form-data
Authorization: Bearer <JWT_TOKEN>
```

**Purpose**: Upload DICOM files to DCM4CHEE archive.

**Request**:
```json
{
  "patient_id": "550e8400-e29b-41d4-a716-446655440000",
  "file": <DICOM binary file>
}
```

**Authorization**: `can_write_patient_obj` permission required

**Response (Success)**:
```json
{
  "status": "success",
  "message": "DICOM uploaded successfully",
  "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
  "dicom_response": {
    "00081199": {
      "vr": "SQ",
      "Value": [...]
    }
  }
}
```

**Response (Already Exists - 409 treated as success)**:
```json
{
  "status": "success",
  "message": "DICOM already exists in DCM4CHEE",
  "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
  "dicom_response": {...}
}
```

**Error Responses**:
```json
// 400 Bad Request
{"error": "No file provided"}

// 403 Forbidden
{"detail": "You do not have permission to upload DICOM for this patient"}

// 502 Bad Gateway
{
  "error": "Failed to upload to DCM4CHEE",
  "status_code": 500,
  "details": "..."
}

// 500 Internal Server Error
{
  "error": "Exception occurred",
  "details": "Connection timeout"
}
```

**Workflow**:
1. Validate patient exists and user has write permission
2. Encode DICOM file as `multipart/related`
3. POST to DCM4CHEE: `{DCM4CHEE_BASEURL}/rs/studies`
4. Extract Study Instance UID from response
5. Create or update `DicomStudy` record
6. Invalidate cache for the study

---

### 3. Query Patient Studies

```http
GET /dicom/studies/?patientId=<external_id>
Authorization: Bearer <JWT_TOKEN>
```

**Purpose**: Retrieve all DICOM studies for a specific patient.

**Query Parameters**:
- `patientId` (required): Patient's external_id (UUID)

**Authorization**: `can_view_patient_obj` permission required

**Response**:
```json
[
  {
    "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
    "study_date": "2025-04-16T10:30:00",
    "study_description": "Chest X-Ray PA and Lateral",
    "study_modalities": ["CR", "DX"],
    "study_series": [
      {
        "series_uid": "1.2.840.113619.2.55.3.2609.2.2.1",
        "series_number": "1",
        "series_instance_count": "2",
        "series_description": "PA View",
        "series_modality": "CR"
      },
      {
        "series_uid": "1.2.840.113619.2.55.3.2609.2.2.2",
        "series_number": "2",
        "series_instance_count": "2",
        "series_description": "Lateral View",
        "series_modality": "CR"
      }
    ]
  }
]
```

**Performance Optimizations**:
- **Caching**: Each study cached for 1 hour (`radiology:dicom:study:{study_uid}`)
- **Parallel Queries**: Uses ThreadPoolExecutor with max 10 workers
- **Lazy Loading**: Only queries DCM4CHEE if not cached

**Error Responses**:
```json
// 404 Not Found
{"detail": "Patient not found"}

// 403 Forbidden
{"detail": "You do not have permission to view this patient"}
```

---

### 4. Query Service Request Studies

```http
GET /dicom/service-requests/?serviceRequestId=<external_id>
Authorization: Bearer <JWT_TOKEN>
```

**Purpose**: Retrieve DICOM studies linked to a specific service request (radiology order).

**Query Parameters**:
- `serviceRequestId` (required): ServiceRequest's external_id (UUID)

**Authorization**: `can_write_service_request` permission required

**Response**: Same format as `/dicom/studies/` endpoint

**Workflow**:
1. Load service request and validate access
2. Query `RadiologyServiceRequest` for linked studies
3. Filter for records with non-null `dicom_study.dicom_study_uid`
4. Fetch metadata from DCM4CHEE (with caching)
5. Return aggregated study list

---

### 5. Webhook Receiver

```http
POST /webhooks/study/
Authorization: <WEBHOOK_SECRET>
Content-Type: application/json
```

**Purpose**: Receive event notifications from DCM4CHEE or external systems.

**Authentication**: Static API key in Authorization header

**Request Payload**:
```json
{
  "service_request_id": "550e8400-e29b-41d4-a716-446655440000",
  "study_id": "1.2.840.113619.2.55.3.2609.2.1.1",
  "event_type": "STUDY_CREATED",
  "timestamp": "2025-04-16T10:30:00Z",
  "additional_data": {...}
}
```

**Response**:
```json
{
  "detail": "Webhook received and saved successfully",
  "record": {
    "external_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "data": {
      "service_request_id": "...",
      "study_id": "..."
    }
  }
}
```

**Error Responses**:
```json
// 400 Bad Request
{"detail": "Invalid JSON payload"}
{"detail": "JSON object expected"}

// 403 Forbidden
{"detail": "Invalid API key"}

// 500 Internal Server Error
{
  "detail": "Service request not found",
  "error": "ServiceRequest matching query does not exist"
}
```

**Workflow**:
1. Validate Authorization header matches `WEBHOOK_SECRET`
2. Create `RadiologyWebhookLogs` entry (audit trail)
3. If payload contains `service_request_id` and `study_id`:
   - Load ServiceRequest
   - Get or create DicomStudy for patient
   - Create or update RadiologyServiceRequest linking them
4. Return success response

---

### 6. Worklist Query

```http
GET /dicom/worklist/?modality=<modality>&from_date=<date>&to_date=<date>&facility=<uuid>
Authorization: <WEBHOOK_SECRET>
```

**Purpose**: Query radiology service requests for worklist management.

**Authentication**: Static API Key (same as webhook)

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `modality` | String | No | Filter by modality (CT, MR, CR, etc.) |
| `from_date` | Date | No | Start date (YYYY-MM-DD or ISO 8601) |
| `to_date` | Date | No | End date (YYYY-MM-DD or ISO 8601) |
| `facility` | UUID | No | Filter by facility |

**Response**:
```json
[
  {
    "service_request_id": "550e8400-e29b-41d4-a716-446655440000",
    "patient": {
      "id": "patient-uuid",
      "name": "John Doe",
      "age": 45,
      "gender": "M"
    },
    "facility": {
      "id": "facility-uuid",
      "name": "City Hospital"
    },
    "modality": "CT",
    "body_part": "Brain",
    "protocol": "CT Brain without Contrast",
    "requested_date": "2025-04-16T10:30:00Z",
    "status": "PENDING"
  }
]
```

**Use Cases**:
- Display pending radiology requests to imaging staff
- Filter by modality for specific scanners
- Schedule imaging appointments
- Track workflow status

---

### 7. Study Report CRUD

```http
GET    /study_report/                     # List reports
POST   /study_report/                     # Create report
GET    /study_report/<uuid>/              # Get specific report
PUT    /study_report/<uuid>/              # Update report
PATCH  /study_report/<uuid>/              # Partial update
DELETE /study_report/<uuid>/              # Soft delete report
```

**Authorization**:
- Read: `can_read_radiology_report`
- Write: `can_write_radiology_report`

**Create Request**:
```json
{
  "study": "dicom-study-uuid",
  "modality": "modality-type-uuid",
  "body_part": "body-part-uuid",
  "scan_protocol": "scan-protocol-uuid",
  "technique": "Standard brain imaging protocol...",
  "findings": "No acute intracranial abnormality...",
  "impression": "Normal CT brain."
}
```

**List Response**:
```json
[
  {
    "id": "report-uuid",
    "study": {
      "id": "study-uuid",
      "dicom_study_uid": "1.2.840.113619...",
      "has_report": true
    },
    "modality": {
      "id": "modality-uuid",
      "display_name": "Computed Tomography"
    },
    "body_part": {
      "id": "body-part-uuid",
      "display_name": "Brain"
    },
    "scan_protocol": {
      "id": "protocol-uuid",
      "display_name": "CT Brain without Contrast"
    },
    "technique": "...",
    "findings": "...",
    "impression": "...",
    "created_by": {
      "id": "user-uuid",
      "username": "dr.smith"
    },
    "created_date": "2025-04-16T10:30:00Z",
    "modified_date": "2025-04-16T11:45:00Z"
  }
]
```

**Query Parameters**:
- `study=<uuid>`: Filter by study external_id
- `ordering=-created_date`: Sort by date (newest first)

**Auto-Generated Features**:
- Audit trail entry created on create/update
- `created_by` and `updated_by` auto-assigned
- `created_datetime` and `last_modified_datetime` auto-managed

---

### 8. Study Report Audit Trail

```http
GET /study-report-audits/?study_report=<uuid>
```

**Purpose**: Retrieve complete change history for a report.

**Authorization**: Same as parent StudyReport

**Response**:
```json
[
  {
    "id": "audit-uuid",
    "study_report": "report-uuid",
    "action": "UPDATED",
    "field_name": "findings",
    "old_value": "Preliminary findings...",
    "new_value": "No acute intracranial abnormality. The ventricles...",
    "created_by": {
      "id": "user-uuid",
      "username": "dr.smith"
    },
    "created_datetime": "2025-04-16T11:45:00Z"
  },
  {
    "id": "audit-uuid-2",
    "study_report": "report-uuid",
    "action": "CREATED",
    "field_name": null,
    "old_value": null,
    "new_value": null,
    "created_by": {
      "id": "user-uuid",
      "username": "dr.smith"
    },
    "created_datetime": "2025-04-16T10:30:00Z"
  }
]
```

**Features**:
- **Read-only**: No create/update/delete operations
- **Automatic**: Entries created by StudyReport save operations
- **Compliance**: HIPAA audit trail for report changes
- **Ordering**: Newest changes first (-created_datetime)

---

### 9. Modality Type Management

```http
GET    /modality_type/                    # List all modalities
POST   /modality_type/                    # Create modality
GET    /modality_type/<uuid>/             # Get specific modality
PUT    /modality_type/<uuid>/             # Update modality
DELETE /modality_type/<uuid>/             # Soft delete
POST   /modality_type/<uuid>/revive/      # Restore deleted
```

**Create Request**:
```json
{
  "display_name": "Computed Tomography",
  "coding": [
    {
      "coding_system": "SNOMED CT",
      "coding_code": "77477000",
      "coding_display": "Computerized axial tomography"
    }
  ]
}
```

**Response**:
```json
{
  "id": "modality-uuid",
  "display_name": "Computed Tomography",
  "coding": [...],
  "created_date": "2025-04-16T10:00:00Z",
  "deleted": false
}
```

**Standard Modalities**:
- CT (Computed Tomography)
- MR (Magnetic Resonance)
- CR (Computed Radiography)
- DX (Digital X-Ray)
- US (Ultrasound)
- NM (Nuclear Medicine)
- PT (Positron Emission Tomography)
- MG (Mammography)

---

### 10. Body Part Management

```http
GET    /body_part/                        # List all body parts
POST   /body_part/                        # Create body part
GET    /body_part/<uuid>/                 # Get specific body part
PUT    /body_part/<uuid>/                 # Update body part
DELETE /body_part/<uuid>/                 # Soft delete
POST   /body_part/<uuid>/revive/          # Restore deleted
```

**Query Parameters**:
- `modality=<uuid>`: Filter by modality type

**Create Request**:
```json
{
  "modality": "ct-modality-uuid",
  "display_name": "Brain",
  "coding": [
    {
      "coding_system": "SNOMED CT",
      "coding_code": "12738006",
      "coding_display": "Brain structure"
    }
  ]
}
```

**Hierarchical Relationship**:
- Each body part belongs to one modality
- Used to filter available body parts based on selected modality
- Example: CT modality → Brain, Chest, Abdomen, Pelvis

---

### 11. Scan Protocol Management

```http
GET    /scan_protocol/                    # List all protocols
POST   /scan_protocol/                    # Create protocol
GET    /scan_protocol/<uuid>/             # Get specific protocol
PUT    /scan_protocol/<uuid>/             # Update protocol
DELETE /scan_protocol/<uuid>/             # Soft delete
POST   /scan_protocol/<uuid>/revive/      # Restore deleted
```

**Query Parameters**:
- `modality=<uuid>`: Filter by modality
- `body_part=<uuid>`: Filter by body part

**Create Request**:
```json
{
  "modality": "ct-modality-uuid",
  "body_part": "brain-body-part-uuid",
  "display_name": "CT Brain without Contrast",
  "coding": [
    {
      "coding_system": "CPT",
      "coding_code": "70450",
      "coding_display": "CT head/brain without contrast"
    }
  ]
}
```

**Hierarchical Relationship**:
```
Modality: CT
└── Body Part: Brain
    ├── Protocol: CT Brain without Contrast
    ├── Protocol: CT Brain with Contrast
    └── Protocol: CT Brain Angiography
```

---

### 12. Template Management

```http
GET    /template/                         # List user's templates
POST   /template/                         # Create template
GET    /template/<uuid>/                  # Get specific template
PUT    /template/<uuid>/                  # Update template
DELETE /template/<uuid>/                  # Soft delete
POST   /template/<uuid>/revive/           # Restore deleted
```

**Authorization**: User can only access their own templates

**Create Request**:
```json
{
  "modality": "ct-modality-uuid",
  "body_part": "brain-body-part-uuid",
  "scan_protocol": "ct-brain-protocol-uuid",
  "technique": "Standard brain imaging...",
  "findings": "Template for normal findings...",
  "impression": "Normal CT brain."
}
```

**Response**:
```json
{
  "id": "template-uuid",
  "user": "user-uuid",
  "modality": {...},
  "body_part": {...},
  "scan_protocol": {...},
  "technique": "...",
  "findings": "...",
  "impression": "...",
  "created_date": "2025-04-16T10:00:00Z"
}
```

**Workflow**:
1. Radiologist creates template for frequently used study types
2. When creating new report, select template
3. Template values pre-fill the report form
4. Radiologist edits as needed for specific case
5. Save as StudyReport (template unchanged)

---

## Service Integrations

### Integration with CARE Backend

#### Patient Management

```python
from care.emr.models.patient import Patient

# Usage in plugin
patient = Patient.objects.get(external_id=request.data.get("patient_id"))
DicomStudy.objects.create(patient=patient, dicom_study_uid=study_uid)
```

**Integration Points**:
- Every DICOM study linked to a Patient
- Patient's `dicom_studies` related manager provides reverse access
- Patient authorization enforced via `AuthorizationController`

---

#### Service Request Workflow

```python
from care.emr.models.service_request import ServiceRequest

# Usage in plugin
service_request = ServiceRequest.objects.get(external_id=sr_external_id)
RadiologyServiceRequest.objects.create(
    service_request=service_request,
    dicom_study=dicom_study,
    raw_data=webhook_payload
)
```

**Integration Points**:
- Links radiology orders to actual imaging studies
- Enables workflow tracking (ordered → performed → reported)
- Supports multiple studies per order (e.g., follow-up scans)

---

#### Authorization Model

```python
from care.security.authorization.base import AuthorizationController

# Permission checks
if not AuthorizationController.call(
    "can_write_patient_obj",
    request.user,
    patient
):
    raise PermissionDenied("...")
```

**Permission Types Used**:
- `can_view_patient_obj`: Read access to patient data
- `can_write_patient_obj`: Upload images for patient
- `can_write_service_request`: Link studies to service requests

**Authorization Hierarchy**:
- Facility-level permissions
- Role-based access (doctor, nurse, radiologist)
- Patient-specific permissions
- Inherited from CARE's existing RBAC system

---

### Integration with DCM4CHEE

#### DICOMweb API

DCM4CHEE implements the DICOMweb standard (DICOM Part 18):

**Base URL**: `{DCM4CHEE_BASEURL}/rs/`

##### STOW-RS (Store Over the Web)

```http
POST /rs/studies
Content-Type: multipart/related; type="application/dicom"
```

**Purpose**: Upload DICOM instances

**Implementation**:
```python
def encode_file_multipart_related(file_obj):
    boundary = f"DICOMBOUNDARY-{uuid.uuid4().hex}"
    file_bytes = file_obj.read()

    body = (
        f"--{boundary}\r\n"
        f"Content-Type: application/dicom\r\n"
        f"Content-Length: {len(file_bytes)}\r\n"
        f"\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    content_type = f'multipart/related; type="application/dicom"; boundary={boundary}'
    return body, content_type

# Upload
response = requests.post(
    f"{DCM4CHEE_BASEURL}/rs/studies",
    data=body,
    headers={"Content-Type": content_type}
)
```

---

##### QIDO-RS (Query based on ID for DICOM Objects)

```http
GET /rs/studies?StudyInstanceUID=<uid>&includefield=<tags>
Accept: application/json
```

**Purpose**: Query study metadata

**Implementation**:
```python
def d_query_study(study_uid):
    response = requests.get(
        f"{DCM4CHEE_BASEURL}/rs/studies",
        headers={"Accept": "application/json"},
        params={
            "StudyInstanceUID": study_uid,
            "includefield": "00081030,00080061"  # Description, Modalities
        }
    )
    return response.json()[0] if response.ok else None
```

---

##### WADO-RS (Web Access to DICOM Objects)

```http
GET /rs/studies/{study_uid}/series/{series_uid}/instances/{instance_uid}/frames/1
```

**Purpose**: Retrieve DICOM frames (handled by OHIF, not plugin directly)

**Flow**:
```
Browser (OHIF) → Nginx → DCM4CHEE → MinIO → Response
```

---

#### DICOM Tag Reference

| Tag | Code | Usage |
|-----|------|-------|
| StudyInstanceUID | 0020000D | Unique study identifier |
| StudyDate | 00080020 | Study date (YYYYMMDD) |
| StudyTime | 00080030 | Study time (HHMMSS) |
| StudyDescription | 00081030 | Study description |
| StudyModalities | 00080061 | Modalities in study |
| SeriesInstanceUID | 0020000E | Unique series identifier |
| SeriesNumber | 00200011 | Series number |
| SeriesDescription | 0008103E | Series description |
| SeriesModality | 00080060 | Series modality (CR, CT, MR) |
| NumberOfSeriesRelatedInstances | 00201209 | Instance count |
| SOPInstanceUID | 00080018 | Instance identifier |

---

### Integration with OHIF Viewer

#### Configuration

**File**: `docker/ohif/app-config.js`

```javascript
window.config = {
  dataSources: [
    {
      namespace: "@ohif/extension-default.dataSourcesModule.dicomweb",
      configuration: {
        name: "DCM4CHEE",
        wadoUriRoot: "http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/wado",
        qidoRoot: "http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs",
        wadoRoot: "http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs",
      }
    }
  ]
};
```

**Important**:
- URLs must be **publicly accessible** from the browser
- In local setup: `http://localhost:32314` (nginx proxy)
- In production: `https://your-domain.com/dicomweb`
- OHIF makes direct HTTP requests (not proxied through Care)

#### Viewer URL Pattern

```
http://localhost:32314/viewer?StudyInstanceUIDs=1.2.840.113619.2.55.3.2609.2.1.1
```

**Integration in Care Frontend**:
```javascript
// In Care React app
const openInOHIF = (studyUid) => {
  const viewerUrl = `http://localhost:32314/viewer?StudyInstanceUIDs=${studyUid}`;
  window.open(viewerUrl, '_blank');
};
```

---

### Integration with MinIO (Object Storage)

#### LDAP Configuration

**File**: `docker/dcm4che/bucketconfig.ldif`

```ldif
dn: dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
changetype: modify
replace: dcmStorageID
dcmStorageID: minio

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

**Setup Steps**:
1. Create bucket in MinIO: `dicom-bucket`
2. Import LDIF into LDAP:
   ```bash
   cd docker/dcm4che
   make ldap-setup
   ```
3. DCM4CHEE reads config from LDAP
4. Images stored in MinIO at `s3://dicom-bucket/studies/{study_uid}/...`

---

## Reports Workflow

### Overview

The care_radiology plugin provides a complete radiology reporting system that allows radiologists to create, edit, and manage structured reports for DICOM studies.

**Key Components**:
1. **ModalityType, BodyPart, ScanProtocol** - Hierarchical configuration
2. **Template** - Pre-filled report templates for common study types
3. **StudyReport** - Actual radiology reports with technique/findings/impression
4. **StudyReportAudit** - Complete change tracking for compliance

---

### Report Creation Workflow

```
┌────────────────────────────────────────────────────────────────────┐
│  Step 1: Configure System (Admin/Setup)                            │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Create ModalityType: CT
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  POST /modality_type/                                               │
│  {                                                                  │
│    "display_name": "Computed Tomography",                          │
│    "coding": [{"system": "SNOMED", "code": "77477000"}]           │
│  }                                                                  │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Create BodyPart: Brain (under CT)
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  POST /body_part/                                                   │
│  {                                                                  │
│    "modality": "<ct-uuid>",                                        │
│    "display_name": "Brain",                                        │
│    "coding": [{"system": "SNOMED", "code": "12738006"}]           │
│  }                                                                  │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Create ScanProtocol: CT Brain without Contrast
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  POST /scan_protocol/                                               │
│  {                                                                  │
│    "modality": "<ct-uuid>",                                        │
│    "body_part": "<brain-uuid>",                                    │
│    "display_name": "CT Brain without Contrast",                   │
│    "coding": [{"system": "CPT", "code": "70450"}]                 │
│  }                                                                  │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Step 2: Create Template (Radiologist - Optional)                  │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Save frequently used report as template
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  POST /template/                                                    │
│  {                                                                  │
│    "modality": "<ct-uuid>",                                        │
│    "body_part": "<brain-uuid>",                                    │
│    "scan_protocol": "<protocol-uuid>",                            │
│    "technique": "Standard brain imaging protocol...",             │
│    "findings": "The brain parenchyma...",                         │
│    "impression": "Normal CT brain."                               │
│  }                                                                  │
│  Response: template-uuid                                           │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Step 3: DICOM Study Uploaded                                      │
└────────────────────────────────────────────────────────────────────┘
    │
    │ (See DICOM Upload Workflow below)
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  DicomStudy created                                                 │
│  - study_uid: "1.2.840.113619..."                                  │
│  - patient: Patient object                                         │
│  - has_report: false (initially)                                   │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Step 4: Create Report (Radiologist)                               │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Option A: From scratch
    │ Option B: From template (pre-fills fields)
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  POST /study_report/                                                │
│  {                                                                  │
│    "study": "<dicom-study-uuid>",                                  │
│    "modality": "<ct-uuid>",                                        │
│    "body_part": "<brain-uuid>",                                    │
│    "scan_protocol": "<protocol-uuid>",                            │
│    "technique": "Non-contrast CT brain...",                       │
│    "findings": "No acute intracranial abnormality...",            │
│    "impression": "Normal CT brain."                               │
│  }                                                                  │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Backend Processing
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  1. Authorize: can_write_radiology_report                          │
│  2. Create StudyReport record                                      │
│  3. Auto-create StudyReportAudit entry:                            │
│     - action: "CREATED"                                            │
│     - field_name: null                                             │
│     - created_by: current user                                     │
│  4. Return success                                                 │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Step 5: Edit Report (Radiologist)                                 │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Update findings after consultation
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  PATCH /study_report/<uuid>/                                        │
│  {                                                                  │
│    "findings": "Updated: Small lacunar infarct...",               │
│    "impression": "Acute lacunar infarct..."                       │
│  }                                                                  │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Backend Processing
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  1. Authorize: can_write_radiology_report                          │
│  2. Load existing StudyReport                                      │
│  3. For each changed field:                                        │
│     Create StudyReportAudit entry:                                 │
│     - action: "UPDATED"                                            │
│     - field_name: "findings" or "impression"                       │
│     - old_value: previous value (JSON)                            │
│     - new_value: new value (JSON)                                 │
│     - created_by: current user                                     │
│  4. Update StudyReport                                             │
│  5. Return success                                                 │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  Step 6: View Audit Trail (Compliance/QA)                          │
└────────────────────────────────────────────────────────────────────┘
    │
    │ Review all changes to report
    ▼
┌────────────────────────────────────────────────────────────────────┐
│  GET /study-report-audits/?study_report=<uuid>                     │
│                                                                     │
│  Response: [                                                        │
│    {                                                                │
│      "action": "UPDATED",                                          │
│      "field_name": "impression",                                   │
│      "old_value": "Normal CT brain.",                             │
│      "new_value": "Acute lacunar infarct...",                     │
│      "created_by": "dr.smith",                                     │
│      "created_datetime": "2025-04-16T14:30:00Z"                   │
│    },                                                               │
│    {                                                                │
│      "action": "CREATED",                                          │
│      "created_by": "dr.smith",                                     │
│      "created_datetime": "2025-04-16T11:00:00Z"                   │
│    }                                                                │
│  ]                                                                  │
└────────────────────────────────────────────────────────────────────┘
```

---

### Report Status Tracking

**has_report Annotation**:

```python
# In DICOM API queries
studies = DicomStudy.objects.filter(patient=patient)

# Enhanced in dicom.py fetch_study()
study_metadata = {
    "study_uid": study_uid,
    "study_date": "...",
    "study_description": "...",
    "has_report": DicomStudy.objects.filter(
        dicom_study_uid=study_uid,
        study_reports__isnull=False
    ).exists()
}
```

**UI Integration**:
```javascript
// In Care Frontend
studies.forEach(study => {
  if (study.has_report) {
    showReportIcon(study);  // Display "Report Available" badge
  } else {
    showCreateReportButton(study);  // Display "Create Report" button
  }
});
```

---

### Template Workflow

**Purpose**: Speed up report generation for common study types

**Example Scenario**:
```
Radiologist frequently reports "Normal CT Brain" studies:
1. Create template with standard findings/impression
2. When new CT brain arrives:
   - Select template from dropdown
   - System pre-fills technique, findings, impression
   - Radiologist reviews and modifies as needed
   - Save as new StudyReport
3. Template remains unchanged for future use
```

**Template API Usage**:
```javascript
// Frontend: Load user's templates
fetch('/api/care_radiology/template/', {
  headers: { 'Authorization': `Bearer ${token}` }
})
.then(r => r.json())
.then(templates => {
  // Filter templates by selected modality/body part
  const matchingTemplates = templates.filter(t =>
    t.modality.id === selectedModality &&
    t.body_part.id === selectedBodyPart
  );

  // Populate dropdown
  showTemplateDropdown(matchingTemplates);
});

// User selects template
function applyTemplate(template) {
  document.getElementById('technique').value = template.technique;
  document.getElementById('findings').value = template.findings;
  document.getElementById('impression').value = template.impression;
}

// Save as new report (template unchanged)
createReport({
  study: currentStudy.id,
  modality: template.modality.id,
  body_part: template.body_part.id,
  scan_protocol: template.scan_protocol.id,
  technique: document.getElementById('technique').value,
  findings: document.getElementById('findings').value,
  impression: document.getElementById('impression').value
});
```

---

### Compliance Features

**HIPAA Compliance**:
1. **Audit Trail**: Every report change logged in StudyReportAudit
2. **User Attribution**: created_by and updated_by tracked automatically
3. **Timestamp**: Precise datetime for all changes
4. **Immutable Logs**: Audit entries read-only, cannot be deleted
5. **Field-Level Tracking**: Know exactly which fields changed and when

**Query Audit Trail**:
```sql
-- All changes to a specific report
SELECT
    sra.action,
    sra.field_name,
    sra.old_value,
    sra.new_value,
    u.username AS modified_by,
    sra.created_datetime
FROM radiology_studyreportaudit sra
JOIN auth_user u ON sra.created_by_id = u.id
WHERE sra.study_report_id = (
    SELECT id FROM radiology_studyreport WHERE external_id = '<report-uuid>'
)
ORDER BY sra.created_datetime DESC;
```

---

## DICOM Workflows

### Upload Workflow

```mermaid
sequenceDiagram
    participant User as User (Browser)
    participant Care as CARE Backend
    participant Plugin as care_radiology
    participant DCM as DCM4CHEE
    participant MinIO as MinIO Storage

    User->>Care: POST /api/care_radiology/dicom/upload/
    Care->>Plugin: Route to DicomViewSet
    Plugin->>Plugin: Validate patient permissions
    Plugin->>Plugin: Encode DICOM as multipart/related
    Plugin->>DCM: POST /rs/studies (STOW-RS)
    DCM->>MinIO: Store DICOM file
    MinIO-->>DCM: Storage confirmation
    DCM-->>Plugin: Return metadata (JSON)
    Plugin->>Plugin: Extract Study UID
    Plugin->>Plugin: Create DicomStudy record
    Plugin->>Plugin: Invalidate cache
    Plugin-->>User: Success response with study_uid
```

**Code Flow**:
```python
# 1. Authorization
patient = Patient.objects.get(external_id=patient_id)
if not AuthorizationController.call("can_write_patient_obj", user, patient):
    raise PermissionDenied()

# 2. Encode file
body, content_type = encode_file_multipart_related(dcm_file)

# 3. Upload to DCM4CHEE
response = requests.post(
    f"{DCM4CHEE_BASEURL}/rs/studies",
    data=body,
    headers={"Content-Type": content_type}
)

# 4. Extract Study UID
ref_sop = d_find(response.json(), DICOM_TAG.ReferencedSOPSQ.value)[0]
instance_uid = d_find(ref_sop, DICOM_TAG.ReferencedInstanceUID.value)[0]
study_uid = d_find(
    d_query_instance(instance_uid),
    DICOM_TAG.StudyInstanceUID.value
)[0]

# 5. Create record
DicomStudy.objects.update_or_create(
    dicom_study_uid=study_uid,
    patient=patient
)

# 6. Cache invalidation
cache.delete(f"radiology:dicom:study:{study_uid}")
```

---

### Query Workflow

```mermaid
sequenceDiagram
    participant User as User (Browser)
    participant Plugin as care_radiology
    participant Cache as Redis Cache
    participant DCM as DCM4CHEE

    User->>Plugin: GET /dicom/studies/?patientId=<uuid>
    Plugin->>Plugin: Validate patient permissions
    Plugin->>Plugin: Load DicomStudy records from DB

    loop For each study (parallel)
        Plugin->>Cache: Check cache key
        alt Cache hit
            Cache-->>Plugin: Return cached metadata
        else Cache miss
            Plugin->>DCM: GET /rs/studies (QIDO-RS)
            DCM-->>Plugin: Study metadata
            Plugin->>DCM: GET /rs/studies/{uid}/series
            DCM-->>Plugin: Series list
            Plugin->>Plugin: Parse DICOM tags
            Plugin->>Cache: Store for 1 hour
        end
    end

    Plugin-->>User: Array of study metadata
```

**Performance Characteristics**:
- **Cache hit**: ~5ms response time
- **Cache miss**: ~200-500ms (DCM4CHEE query)
- **Parallel queries**: Max 10 concurrent DCM4CHEE requests
- **Cache TTL**: 1 hour

---

### Retrieve/View Workflow

```mermaid
sequenceDiagram
    participant User as Browser (OHIF)
    participant Nginx as Nginx Proxy
    participant Care as CARE Backend
    participant DCM as DCM4CHEE
    participant MinIO as MinIO Storage

    User->>Nginx: GET /dicomweb/rs/studies/{uid}/series/{sid}/instances/...
    Nginx->>Care: auth_request /authenticate
    Care-->>Nginx: 200 OK (JWT valid)
    Nginx->>DCM: GET /rs/studies/{uid}/series/{sid}/instances/...
    DCM->>MinIO: Retrieve DICOM file
    MinIO-->>DCM: DICOM data
    DCM->>DCM: Extract frames/metadata
    DCM-->>Nginx: DICOM response (WADO-RS)
    Nginx-->>User: DICOM data
    User->>User: Render in OHIF viewer
```

**Nginx Configuration**:
```nginx
location /dicomweb/ {
    # Validate JWT with Care
    auth_request /authenticate;

    # Strip auth headers before proxying
    proxy_set_header authorization "";
    proxy_set_header Authorization "";

    # Proxy to DCM4CHEE
    proxy_pass http://arc:8080;
    rewrite /dicomweb(.*) $1 break;
}

location = /authenticate {
    internal;
    proxy_pass http://host.docker.internal:9000/api/care_radiology/dicom/authenticate/;
}
```

---

### Webhook Workflow

```mermaid
sequenceDiagram
    participant External as External System
    participant Plugin as care_radiology
    participant DB as PostgreSQL

    External->>Plugin: POST /webhooks/study/
    Plugin->>Plugin: Validate API key
    Plugin->>DB: Create RadiologyWebhookLogs (audit)

    alt Contains service_request_id and study_id
        Plugin->>DB: Load ServiceRequest
        Plugin->>DB: Get/Create DicomStudy
        Plugin->>DB: Create RadiologyServiceRequest
        Plugin-->>External: Success with record
    else Missing required fields
        Plugin-->>External: Success (logged only)
    end
```

**Use Cases**:
1. **DCM4CHEE Event Notification**: Study created/updated in PACS
2. **External Modality Integration**: CT/MRI machine uploads complete
3. **Third-party DICOM Router**: Forward events from other systems

**Example Webhook**:
```bash
curl -X POST http://localhost:9000/api/care_radiology/webhooks/study/ \
  -H "Authorization: my-webhook-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "service_request_id": "550e8400-e29b-41d4-a716-446655440000",
    "study_id": "1.2.840.113619.2.55.3.2609.2.1.1",
    "event_type": "STUDY_CREATED",
    "timestamp": "2025-04-16T10:30:00Z"
  }'
```

---

## Authentication & Authorization

### JWT Authentication (Care Users)

**Used By**:
- `/dicom/upload/`
- `/dicom/studies/`
- `/dicom/service-requests/`

**Flow**:
```python
# Care's default authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

# Applied automatically by Care's REST framework config
```

**Token Format**:
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

### Static API Key (Webhooks & Worklist)

**Used By**:
- `/webhooks/study/`
- `/dicom/worklist/`

**Implementation**:
```python
class StaticAPIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        STATIC_API_KEY = plugin_settings.CARE_RADIOLOGY_WEBHOOK_SECRET

        if api_key == STATIC_API_KEY:
            return (AnonymousUser(), None)

        raise AuthenticationFailed("Invalid API key")
```

**Usage**:
```http
Authorization: my-secure-webhook-secret-here
```

**Purpose**:
- Allows external systems (DCM4CHEE, modalities) to access specific endpoints
- No user context required
- Simple shared secret authentication

---

### Authorization Matrix

| Endpoint | Authentication | Authorization | Purpose |
|----------|---------------|---------------|---------|
| **DICOM Operations** ||||
| `POST /dicom/authenticate/` | None | None | Nginx auth check |
| `POST /dicom/upload/` | JWT | `can_write_patient_obj` | Upload images |
| `GET /dicom/studies/` | JWT | `can_view_patient_obj` | View patient studies |
| `GET /dicom/service-requests/` | JWT | `can_write_service_request` | View order studies |
| `GET /dicom/worklist/` | Static API Key | None | Query pending requests |
| **Webhooks** ||||
| `POST /webhooks/study/` | Static API Key | None | External events |
| **Reporting** ||||
| `GET /study_report/` | JWT | `can_read_radiology_report` | List reports |
| `POST /study_report/` | JWT | `can_write_radiology_report` | Create report |
| `PUT /study_report/<id>/` | JWT | `can_write_radiology_report` | Update report |
| `DELETE /study_report/<id>/` | JWT | `can_write_radiology_report` | Delete report |
| `GET /study-report-audits/` | JWT | `can_read_radiology_report` | View audit trail |
| **Configuration** ||||
| `CRUD /modality_type/` | JWT | Standard CARE permissions | Manage modalities |
| `CRUD /body_part/` | JWT | Standard CARE permissions | Manage body parts |
| `CRUD /scan_protocol/` | JWT | Standard CARE permissions | Manage protocols |
| `CRUD /template/` | JWT | User owns template | Manage templates |

---

### Report Permissions

**Permission Enum** (`RadiologyReportPermissions`):

```python
class RadiologyReportPermissions(Enum):
    can_write_radiology_report = "can_write_radiology_report"
    can_read_radiology_report = "can_read_radiology_report"
```

**Role Mappings**:

| Permission | Roles with Access |
|------------|-------------------|
| `can_write_radiology_report` | FACILITY_ADMIN, ADMIN, NURSE |
| `can_read_radiology_report` | FACILITY_ADMIN, ADMINISTRATOR, ADMIN, STAFF, DOCTOR, NURSE, VOLUNTEER, PHARMACIST |

**Authorization Handler**:
```python
class RadiologyReportAccess(AuthorizationHandler):
    def can_write_radiology_report(self, user, study_report=None):
        return self.check_permission_in_facility_organization(
            user,
            "can_write_radiology_report",
            study_report.study.patient if study_report else None
        )

    def can_read_radiology_report(self, user, study_report=None):
        return self.check_permission_in_facility_organization(
            user,
            "can_read_radiology_report",
            study_report.study.patient if study_report else None
        )
```

**Permission Check Example**:
```python
# In StudyReportViewSet
def verify_report_permission(self, type='read'):
    permission = f"can_{type}_radiology_report"
    study = DicomStudy.objects.get(external_id=self.request.data.get('study'))

    if not AuthorizationController.call(
        permission,
        self.request.user,
        study.patient
    ):
        raise PermissionDenied(f"No {type} permission for radiology reports")
```

---

### Permission Checks Implementation

```python
from care.security.authorization.base import AuthorizationController

# Example: Upload endpoint
patient = Patient.objects.get(external_id=patient_id)

if not AuthorizationController.call(
    "can_write_patient_obj",
    self.request.user,
    patient
):
    raise PermissionDenied(
        "You do not have permission to upload DICOM for this patient"
    )
```

**Permission System**:
- Facility-based: Users can only access patients in their facilities
- Role-based: Different permissions for doctors, nurses, radiologists
- Object-level: Per-patient and per-service-request checks
- Inherited from CARE's RBAC system (no custom logic needed)

---

## Docker Infrastructure

### Service Topology

```
┌─────────────────────────────────────────────────────────────┐
│  Host Machine (macOS)                                        │
│                                                              │
│  ┌────────────────┐         ┌──────────────────┐           │
│  │ CARE Backend   │         │ PostgreSQL       │           │
│  │ (Nix)          │         │ (Port 5432)      │           │
│  │ Port 9000      │         │                  │           │
│  └────────────────┘         └──────────────────┘           │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Docker Network                                       │  │
│  │                                                       │  │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐         │  │
│  │  │  LDAP    │  │    Arc    │  │   OHIF   │         │  │
│  │  │  :3890   │  │   :8080   │  │   :3000  │         │  │
│  │  └────┬─────┘  └─────┬─────┘  └──────────┘         │  │
│  │       │              │                               │  │
│  │       └──────────────┴─────────────────────┐        │  │
│  │                                             │        │  │
│  │                   ┌────────────────────┐    │        │  │
│  │                   │  Nginx Proxy       │    │        │  │
│  │                   │  :32314 (public)   │◄───┘        │  │
│  │                   └────────────────────┘             │  │
│  │                                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  host.docker.internal → Connects Docker to host            │
└─────────────────────────────────────────────────────────────┘
```

### Port Mapping

| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| LDAP | 389 | 3890 | Directory service |
| DCM4CHEE | 8080 | 8080 | DICOM archive API |
| OHIF | 80 | 3000 | Direct viewer access |
| Nginx | 80 | 32314 | Public proxy endpoint |

### Volume Mounts

```yaml
services:
  nginx:
    volumes:
      - ./docker/nginx-proxy/nginx.conf:/etc/nginx/nginx.conf:ro
```

**Important**:
- `:ro` = Read-only mount
- Configuration changes require container restart
- No persistent data stored (images in MinIO, metadata in PostgreSQL)

---

## Configuration

### Environment Variables

#### Required Settings

```bash
# DCM4CHEE Connection
CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL=http://arc:8080/dcm4chee-arc/aets/DCM4CHEE

# Webhook Security
CARE_RADIOLOGY_WEBHOOK_SECRET=your-secure-webhook-secret
```

#### Optional Settings (Inherited from CARE)

```bash
# Database
DATABASE_URL=postgres://postgres:postgres@localhost:5432/dicom

# Cache
REDIS_URL=redis://localhost:6380

# Storage (MinIO)
BUCKET_ENDPOINT=http://localhost:4566
BUCKET_EXTERNAL_ENDPOINT=http://localhost:4566
```

---

### Plugin Configuration in Care

**File**: `care/plug_config.py`

#### Local Development

```python
care_radiology_plugin = Plug(
    name="care_radiology",
    package_name="/app/care_radiology",  # Editable install
    version="",  # Empty for local dev
    configs={
        "DCM4CHEE_DICOMWEB_BASEURL": "http://arc:8080/dcm4chee-arc/aets/DCM4CHEE",
        "WEBHOOK_SECRET": "local-dev-secret"
    },
)

plugs = [care_radiology_plugin]
```

#### Production

```python
care_radiology_plugin = Plug(
    name="care_radiology",
    package_name="git+https://github.com/10bedicu/care_radiology.git",
    version="@main",  # Or specific tag: @v1.0.0
    configs={
        "DCM4CHEE_DICOMWEB_BASEURL": os.environ.get("DCM4CHEE_BASEURL"),
        "WEBHOOK_SECRET": os.environ.get("RADIOLOGY_WEBHOOK_SECRET")
    },
)

plugs = [care_radiology_plugin]
```

---

### DCM4CHEE Database Setup

**File**: `docker/dcm4che/Makefile`

```makefile
CONTAINER_NAME = care-db-1
DB_NAME = dicom
DB_USER = postgres

PSQL = psql -h localhost -p 5432 -U $(DB_USER) -d $(DB_NAME)

setup-dicom-db:
	@echo "Running SQL scripts..."
	@$(PSQL) < ./sql-scripts/10_create-psql.sql
	@$(PSQL) < ./sql-scripts/20_create-fk-index.sql
	@$(PSQL) < ./sql-scripts/30_create-case-insensitive-index.sql
	@echo "Done!"
```

**Usage**:
```bash
cd docker/dcm4che
make setup-dicom-db
```

**What it does**:
- Creates DCM4CHEE tables (studies, series, instances, etc.)
- Sets up foreign key constraints
- Creates performance indexes
- Must be run before starting DCM4CHEE container

---

### LDAP Configuration for MinIO

**File**: `docker/dcm4che/bucketconfig.ldif`

**Purpose**: Tells DCM4CHEE to store images in MinIO bucket

**Import**:
```bash
cd docker/dcm4che
make ldap-setup
# Password: dcm4chee
```

**Validation**:
```bash
# Query LDAP to verify
ldapsearch -x -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 \
  -W \
  -b "dcmStorageID=minio,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org"
```

---

## Deployment Guide

### Local Development Setup

#### Prerequisites

- macOS with Docker Desktop
- PostgreSQL installed locally (port 5432)
- Redis installed locally (port 6380)
- Care backend running via nix (port 9000)
- MinIO running (optional, can use localstack)

#### Step-by-Step

1. **Clone the plugin**:
   ```bash
   cd care
   git clone git@github.com:10bedicu/care_radiology.git
   ```

2. **Add to plug_config.py**:
   ```python
   care_radiology_plugin = Plug(
       name="care_radiology",
       package_name="/app/care_radiology",
       version="",
       configs={
           "DCM4CHEE_DICOMWEB_BASEURL": "http://arc:8080/dcm4chee-arc/aets/DCM4CHEE",
           "WEBHOOK_SECRET": "local-dev-secret"
       },
   )
   plugs = [care_radiology_plugin]
   ```

3. **Modify plugs/manager.py** (editable install):
   ```python
   subprocess.check_call(
       [sys.executable, "-m", "pip", "install", "-e", *packages]
   )
   ```

4. **Create dicom database**:
   ```bash
   psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE dicom;"
   ```

5. **Setup DCM4CHEE schema**:
   ```bash
   cd care_radiology/docker/dcm4che
   make setup-dicom-db
   ```

6. **Start Docker services**:
   ```bash
   cd care_radiology
   docker compose -f docker-compose.radiology.yaml up -d
   ```

7. **Configure LDAP for MinIO**:
   ```bash
   cd docker/dcm4che
   make ldap-setup
   # Enter password: dcm4chee
   ```

8. **Verify services**:
   ```bash
   docker compose -f docker-compose.radiology.yaml ps
   # All services should be "running"
   ```

9. **Access endpoints**:
   - OHIF Viewer: http://localhost:32314
   - DCM4CHEE Admin: http://localhost:8080/dcm4chee-arc/ui2
   - Care API: http://localhost:9000/api/care_radiology/

---

### Production Deployment

#### Infrastructure Requirements

**Compute**:
- Care Backend: 2 vCPU, 4GB RAM
- DCM4CHEE: 4 vCPU, 8GB RAM
- PostgreSQL: 2 vCPU, 4GB RAM, 100GB SSD
- Redis: 1 vCPU, 2GB RAM

**Storage**:
- PostgreSQL: 100GB (metadata)
- MinIO/S3: Unlimited (DICOM images, ~1-10GB per study)

**Network**:
- Ingress: HTTPS (443)
- Egress: HTTPS to external webhooks
- Internal: Service-to-service communication

---

#### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Load Balancer / CDN                                             │
│  - SSL Termination                                               │
│  - DDoS Protection                                               │
└─────────────┬───────────────────────────────────────────────────┘
              │
    ┌─────────▼─────────────────────────────────┐
    │  Nginx Ingress Controller                 │
    │  - /api/care_radiology/* → Care Backend   │
    │  - /dicomweb/* → DCM4CHEE (auth_request)  │
    │  - / → OHIF Viewer                        │
    └─────────┬────────────────┬────────────────┘
              │                │
    ┌─────────▼──────┐  ┌──────▼────────────┐
    │  Care Backend  │  │  DCM4CHEE         │
    │  (Kubernetes)  │  │  (Kubernetes)     │
    └─────────┬──────┘  └──────┬────────────┘
              │                │
    ┌─────────▼────────────────▼────────────┐
    │  PostgreSQL (RDS / CloudSQL)          │
    │  - care database                      │
    │  - dicom database                     │
    └────────────────────────────────────────┘
              │
    ┌─────────▼────────────────┐
    │  S3 / Google Cloud       │
    │  Storage                 │
    │  - DICOM images          │
    └──────────────────────────┘
```

---

#### Deployment Steps

1. **Database Setup**:
   ```bash
   # Create databases
   CREATE DATABASE care;
   CREATE DATABASE dicom;

   # Run DCM4CHEE schema
   psql -d dicom -f sql-scripts/10_create-psql.sql
   psql -d dicom -f sql-scripts/20_create-fk-index.sql
   psql -d dicom -f sql-scripts/30_create-case-insensitive-index.sql
   ```

2. **Object Storage Setup**:
   ```bash
   # Create S3 bucket
   aws s3 mb s3://dicom-images-prod

   # Set lifecycle policy
   aws s3api put-bucket-lifecycle-configuration \
     --bucket dicom-images-prod \
     --lifecycle-configuration file://lifecycle.json
   ```

3. **Configure DCM4CHEE**:
   - Set environment variables for S3
   - Import LDAP configuration
   - Configure storage tier (ONLINE/NEARLINE/ARCHIVE)

4. **Deploy Care Backend**:
   ```yaml
   # Kubernetes deployment
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: care-backend
   spec:
     replicas: 3
     template:
       spec:
         containers:
         - name: care
           image: care:latest
           env:
           - name: CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL
             value: "http://dcm4chee-service:8080/dcm4chee-arc/aets/DCM4CHEE"
           - name: CARE_RADIOLOGY_WEBHOOK_SECRET
             valueFrom:
               secretKeyRef:
                 name: care-secrets
                 key: webhook-secret
   ```

5. **Configure Monitoring**:
   - Prometheus metrics for API performance
   - DCM4CHEE logs for DICOM errors
   - Sentry for error tracking
   - CloudWatch/Stackdriver for infrastructure

6. **Setup Backup Strategy**:
   - PostgreSQL: Daily automated backups
   - S3/GCS: Versioning enabled
   - DCM4CHEE config: LDAP backup
   - Disaster recovery plan

---

### Monitoring & Observability

#### Health Checks

```http
GET /api/care_radiology/health
```

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-04-16T10:30:00Z"
}
```

#### Metrics to Monitor

| Metric | Alert Threshold | Action |
|--------|-----------------|--------|
| DICOM upload latency | > 30s | Check DCM4CHEE/MinIO |
| Cache hit rate | < 70% | Increase TTL or memory |
| DCM4CHEE connection errors | > 5% | Check network/service |
| Webhook processing failures | > 1% | Check logs |
| PostgreSQL connections | > 80% | Scale up |

#### Logging

**Structured Logs**:
```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "DICOM upload successful",
    extra={
        "patient_id": patient.external_id,
        "study_uid": study_uid,
        "user_id": request.user.id,
        "duration_ms": 1234
    }
)
```

**Log Aggregation**: ELK Stack, Splunk, or Cloud Logging

---

## Security Considerations

### Data Protection

1. **DICOM PHI (Protected Health Information)**:
   - All DICOM files contain patient identifiers
   - Stored encrypted at rest (S3/GCS encryption)
   - Transmitted over HTTPS only
   - Access controlled via CARE's RBAC

2. **Database Encryption**:
   - PostgreSQL: Encryption at rest (disk encryption)
   - Redis: TLS for cache connections
   - Backups: Encrypted before storage

3. **Network Security**:
   - Internal services: Private network only
   - External API: HTTPS with TLS 1.2+
   - DCM4CHEE: Not exposed publicly, behind nginx

---

### Access Control

1. **API Authentication**:
   - JWT tokens with short expiry (10 minutes)
   - Refresh token rotation
   - IP whitelisting for webhooks

2. **Authorization**:
   - Facility-level isolation
   - Role-based permissions
   - Audit logs for all access

3. **Webhook Security**:
   - Static API key (rotate quarterly)
   - Request signature validation (future)
   - Rate limiting

---

### Compliance

**HIPAA Considerations**:
- Audit trail: All access logged
- Data encryption: At rest and in transit
- Access control: Facility-based isolation
- Backup and recovery: Automated and tested

**DICOM Conformance**:
- DICOMweb standard (Part 18)
- Study-level query/retrieve
- Secure transfer (HTTPS)

---

## Troubleshooting

### Common Issues

#### 1. DCM4CHEE Connection Errors

**Symptom**: `502 Bad Gateway` on upload

**Diagnosis**:
```bash
# Check DCM4CHEE logs
docker logs care_radiology-arc-1

# Test connection
curl http://localhost:8080/dcm4chee-arc/ui2
```

**Solutions**:
- Verify DCM4CHEE is running
- Check `WILDFLY_WAIT_FOR: ldap:389` (DCM4CHEE waits for LDAP)
- Ensure PostgreSQL connection works from container

---

#### 2. LDAP Configuration Issues

**Symptom**: DCM4CHEE starts but can't store images

**Diagnosis**:
```bash
# Check LDAP logs
docker logs care_radiology-ldap-1

# Query storage config
ldapsearch -x -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 -W \
  -b "dcmStorageID=minio,..."
```

**Solutions**:
- Re-import `bucketconfig.ldif`
- Verify MinIO bucket exists
- Check S3 credentials in LDIF

---

#### 3. Nginx Authentication Failures

**Symptom**: `403 Forbidden` when accessing OHIF

**Diagnosis**:
```bash
# Check nginx logs
docker logs care_radiology-nginx-1

# Test auth endpoint directly
curl -H "Authorization: Bearer <token>" \
  http://localhost:9000/api/care_radiology/dicom/authenticate/
```

**Solutions**:
- Verify Care backend is running on port 9000
- Check `host.docker.internal` resolves (Docker setting)
- Test JWT token validity

---

#### 4. Cache Performance Issues

**Symptom**: Slow query responses

**Diagnosis**:
```bash
# Check cache hit rate
redis-cli
> INFO stats
```

**Solutions**:
- Increase cache TTL (currently 1 hour)
- Scale Redis vertically
- Add cache warming for common queries

---

## Future Enhancements

### Planned Features

1. **Reporting Workflow**:
   - Structured radiology reports
   - Link reports to DICOM studies
   - Report templates (chest X-ray, CT brain, etc.)

2. **DICOM Modality Worklist**:
   - Push orders to imaging devices
   - Automatic patient demographics
   - Study tracking

3. **AI Integration**:
   - Auto-segmentation
   - CAD (Computer-Aided Detection)
   - Triage critical findings

4. **Advanced Querying**:
   - Search by modality, body part, date range
   - Full-text search in descriptions
   - Study comparison tools

5. **Performance**:
   - Image compression
   - Progressive loading
   - CDN for WADO-RS

---

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| **DICOM** | Digital Imaging and Communications in Medicine standard |
| **PACS** | Picture Archiving and Communication System |
| **DICOMweb** | RESTful web services for DICOM (Part 18 of standard) |
| **QIDO-RS** | Query based on ID for DICOM Objects - RESTful Services |
| **WADO-RS** | Web Access to DICOM Objects - RESTful Services |
| **STOW-RS** | Store Over the Web - RESTful Services |
| **Study** | A collection of images from a single imaging session |
| **Series** | A set of images within a study (e.g., PA view, Lateral view) |
| **Instance** | A single DICOM image or frame |
| **Modality** | Type of imaging equipment (CR, CT, MR, US, etc.) |
| **SOPInstanceUID** | Unique identifier for a DICOM instance |
| **StudyInstanceUID** | Unique identifier for a DICOM study |

---

### References

- [DICOM Standard](https://www.dicomstandard.org/)
- [DICOMweb Specification](https://www.dicomstandard.org/using/dicomweb)
- [DCM4CHEE Documentation](https://github.com/dcm4che/dcm4chee-arc-light/wiki)
- [OHIF Viewer Documentation](https://docs.ohif.org/)
- [CARE Backend Documentation](https://care-be-docs.ohc.network/)

---

*Document Version: 1.0*
*Last Updated: 2025-04-16*
*Maintained by: Care Development Team*
