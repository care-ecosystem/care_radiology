# API Specification Review - Best Practices & FHIR Enhancement Recommendations

**Document Version**: 1.0
**Review Date**: 2026-04-23
**Reviewer**: Technical Architecture Review
**Status**: Recommendations for Implementation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Critical Issues](#critical-issues)
3. [REST API Best Practices](#rest-api-best-practices)
4. [Database Design Issues](#database-design-issues)
5. [FHIR Compliance Gaps](#fhir-compliance-gaps)
6. [Security Concerns](#security-concerns)
7. [Performance Optimizations](#performance-optimizations)
8. [API Versioning](#api-versioning)
9. [Documentation Improvements](#documentation-improvements)
10. [Implementation Priority Matrix](#implementation-priority-matrix)

---

## Executive Summary

### Overall Assessment

The care_radiology API specification is **well-structured and functional** but has several gaps in REST best practices, FHIR compliance, and production-readiness. This review identifies **38 recommendations** across 7 categories.

### Key Findings

**Strengths**:
- ✅ Comprehensive database schema with proper indexing
- ✅ Good use of soft deletes for audit trail
- ✅ ThreadPoolExecutor for parallel queries
- ✅ Redis caching implementation
- ✅ Detailed authorization checks

**Critical Gaps**:
- ❌ No API versioning strategy
- ❌ Missing FHIR-compliant endpoints
- ❌ Inconsistent REST naming conventions
- ❌ No pagination documentation
- ❌ Missing report status workflow
- ❌ No encounter linkage
- ❌ Limited DICOM metadata caching in database

### Priority Recommendations

| Priority | Issue | Impact |
|----------|-------|--------|
| 🔴 **P0** | Add API versioning (`/v1/` prefix) | Breaking changes management |
| 🔴 **P0** | Implement FHIR endpoints | Healthcare interoperability |
| 🔴 **P0** | Add report status workflow | Clinical safety |
| 🟡 **P1** | Fix REST naming inconsistencies | Developer experience |
| 🟡 **P1** | Add pagination to all list endpoints | Performance at scale |
| 🟢 **P2** | Link reports to encounters | Clinical context |
| 🟢 **P2** | Add DICOM metadata caching | Query performance |

---

## Critical Issues

### 1. Missing API Versioning

**Severity**: 🔴 **Critical**

**Current State**:
```
/api/care_radiology/dicom/upload/
/api/care_radiology/study_report/
```

**Issue**: No version prefix makes breaking changes impossible without affecting all clients.

**Recommendation**:
```
/api/care_radiology/v1/dicom/upload/
/api/care_radiology/v1/study_report/
/api/care_radiology/v2/fhir/ImagingStudy/     # Future FHIR endpoints
```

**Implementation**:
```python
# urls.py
urlpatterns = [
    path('v1/', include('care_radiology.api.v1.urls')),
    path('v2/', include('care_radiology.api.v2.urls')),  # Future
]
```

**References**: [REST API Versioning Best Practices](https://www.troyhunt.com/your-api-versioning-is-wrong-which-is/)

---

### 2. No FHIR-Compliant Endpoints

**Severity**: 🔴 **Critical**

**Current State**: Only custom Django REST endpoints, no FHIR resources.

**Issue**: Healthcare systems expect FHIR R4 resources (ImagingStudy, DiagnosticReport, etc.) for interoperability.

**Recommendation**: Add FHIR endpoints alongside existing API.

**Proposed Endpoints**:

```
# FHIR R4 Endpoints (new)
GET  /api/care_radiology/v1/fhir/ImagingStudy?patient=<uuid>
GET  /api/care_radiology/v1/fhir/ImagingStudy/<id>
GET  /api/care_radiology/v1/fhir/DiagnosticReport?subject=<uuid>
POST /api/care_radiology/v1/fhir/DiagnosticReport
GET  /api/care_radiology/v1/fhir/ServiceRequest?patient=<uuid>
GET  /api/care_radiology/v1/fhir/Endpoint          # DICOMweb endpoint metadata

# Existing endpoints (keep for backward compatibility)
GET  /api/care_radiology/v1/dicom/studies/
POST /api/care_radiology/v1/study_report/
```

**Implementation Strategy**:

```python
# Install django-fhir library
# pip install fhir.resources

from fhir.resources.imagingstudy import ImagingStudy
from fhir.resources.diagnosticreport import DiagnosticReport

class FHIRImagingStudyViewSet(ViewSet):
    """FHIR R4 ImagingStudy endpoint"""

    @action(detail=False, methods=["get"])
    def search(self, request):
        patient_id = request.query_params.get("patient")
        subject_ref = request.query_params.get("subject")

        # Query DicomStudy records
        studies = DicomStudy.objects.filter(patient__external_id=patient_id)

        # Convert to FHIR ImagingStudy resources
        fhir_resources = []
        for study in studies:
            imaging_study = ImagingStudy(
                id=str(study.external_id),
                status="available",
                subject={"reference": f"Patient/{study.patient.external_id}"},
                identifier=[{
                    "system": "urn:dicom:uid",
                    "value": f"urn:oid:{study.dicom_study_uid}"
                }],
                # ... populate series, modality, etc.
            )
            fhir_resources.append(imaging_study.dict())

        return Response({
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(fhir_resources),
            "entry": [{"resource": r} for r in fhir_resources]
        })
```

**References**: See [FHIR_ANALYSIS.md](./FHIR_ANALYSIS.md) for complete mapping.

---

### 3. Missing Report Status Workflow

**Severity**: 🔴 **Critical**

**Current State**: No status field on `StudyReport` model.

**Issue**: Reports cannot track workflow states (draft, preliminary, final, amended, cancelled). This is a **clinical safety issue** - users cannot distinguish between preliminary and final reports.

**Recommendation**: Add status field with workflow constraints.

**Database Change**:

```python
class StudyReport(EMRBaseModel):
    study = ForeignKey(DicomStudy, on_delete=CASCADE)
    modality = ForeignKey(ModalityType, on_delete=CASCADE)
    body_part = ForeignKey(BodyPart, on_delete=CASCADE)
    scan_protocol = ForeignKey(ScanProtocol, on_delete=CASCADE)

    # NEW: Status workflow
    status = CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("preliminary", "Preliminary"),
            ("final", "Final"),
            ("amended", "Amended"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        db_index=True
    )

    # NEW: Timestamps for status transitions
    finalized_datetime = DateTimeField(null=True, blank=True)
    amended_datetime = DateTimeField(null=True, blank=True)

    technique = TextField(null=True, blank=True)
    findings = TextField(null=True, blank=True)
    impression = TextField(null=True, blank=True)

    # Existing fields...
    created_datetime = DateTimeField(default=timezone.now)
    last_modified_datetime = DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Prevent multiple final reports for same study
            models.UniqueConstraint(
                fields=["study"],
                condition=models.Q(status="final", deleted=False),
                name="unique_final_report_per_study"
            )
        ]
```

**API Changes**:

```python
# Request
POST /api/care_radiology/v1/study_report/
{
  "study": "...",
  "status": "draft",  # NEW: Required field
  "modality": "...",
  "body_part": "...",
  "scan_protocol": "...",
  "technique": "...",
  "findings": "...",
  "impression": "..."
}

# Status transition endpoint
PATCH /api/care_radiology/v1/study_report/{id}/finalize/
{
  "status": "final"
}
```

**Workflow Rules**:

```python
ALLOWED_TRANSITIONS = {
    "draft": ["preliminary", "final", "cancelled"],
    "preliminary": ["final", "cancelled"],
    "final": ["amended"],
    "amended": ["amended"],  # Can amend multiple times
    "cancelled": [],  # Terminal state
}

def validate_status_transition(old_status, new_status):
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, []):
        raise ValidationError(
            f"Cannot transition from {old_status} to {new_status}"
        )
```

**FHIR Alignment**: This matches `DiagnosticReport.status` in FHIR R4.

---

## REST API Best Practices

### 4. Inconsistent Resource Naming

**Severity**: 🟡 **Medium**

**Current Issues**:

```
❌ /dicom/studies/              # Plural, good
❌ /study_report/                # Singular, inconsistent
❌ /study-report-audits/         # Hyphenated, inconsistent with study_report
❌ /modality_type/               # Underscore, should be hyphen or camelCase
```

**Recommendation**: Use consistent kebab-case plurals for all resources.

```
✅ /dicom/studies/
✅ /study-reports/
✅ /study-report-audits/
✅ /modality-types/
✅ /body-parts/
✅ /scan-protocols/
✅ /templates/
```

**Implementation**:

```python
# urls.py
router.register(r'study-reports', StudyReportViewSet, basename='study-report')
router.register(r'modality-types', ModalityTypeViewSet, basename='modality-type')
```

**Impact**: Breaking change - requires API versioning (see Issue #1).

---

### 5. Missing Pagination Configuration

**Severity**: 🟡 **Medium**

**Current State**: Documentation mentions pagination but doesn't specify configuration.

**Issue**: Unclear what default page size is, how to request different page sizes, or max limits.

**Recommendation**: Document and configure pagination.

**Documentation Addition**:

```markdown
## Pagination

All list endpoints support pagination with the following parameters:

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| page | Integer | 1 | - | Page number |
| page_size | Integer | 50 | 100 | Results per page |

**Request**:
GET /api/care_radiology/v1/study-reports/?page=2&page_size=25

**Response**:
{
  "count": 150,
  "next": "http://.../v1/study-reports/?page=3&page_size=25",
  "previous": "http://.../v1/study-reports/?page=1&page_size=25",
  "results": [ ... ]
}
```

**Configuration**:

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'MAX_PAGE_SIZE': 100,
}
```

---

### 6. No Bulk Operations Support

**Severity**: 🟢 **Low**

**Current State**: Only single-resource CRUD operations.

**Issue**: Cannot create/update multiple reports in one request (common for batch imports).

**Recommendation**: Add bulk endpoints for common operations.

```python
# Bulk create reports
POST /api/care_radiology/v1/study-reports/bulk/
{
  "reports": [
    { "study": "...", "modality": "...", ... },
    { "study": "...", "modality": "...", ... }
  ]
}

# Response
{
  "created": 2,
  "failed": 0,
  "results": [
    { "external_id": "...", "status": "created" },
    { "external_id": "...", "status": "created" }
  ]
}
```

---

### 7. Missing HATEOAS Links

**Severity**: 🟢 **Low**

**Current State**: Responses don't include related resource links.

**Issue**: Clients must construct URLs manually.

**Recommendation**: Add `_links` object to responses.

```json
{
  "external_id": "a50e8400-e29b-41d4-a716-446655440000",
  "study_id": "650e8400-e29b-41d4-a716-446655440001",
  "status": "final",
  "modality": "CT Scan",
  "_links": {
    "self": {
      "href": "/api/care_radiology/v1/study-reports/a50e8400-e29b-41d4-a716-446655440000"
    },
    "study": {
      "href": "/api/care_radiology/v1/dicom/studies/650e8400-e29b-41d4-a716-446655440001"
    },
    "audits": {
      "href": "/api/care_radiology/v1/study-report-audits/?study_report=a50e8400-e29b-41d4-a716-446655440000"
    },
    "patient": {
      "href": "/api/emr/v1/patients/550e8400-e29b-41d4-a716-446655440000"
    }
  }
}
```

---

### 8. Inconsistent Error Response Format

**Severity**: 🟡 **Medium**

**Current State**: Multiple error formats.

```json
// DRF default
{ "detail": "Not found." }

// Custom upload endpoint
{ "error": "Failed to upload", "status_code": 500, "details": "..." }

// Validation errors
{ "field_name": ["Error message"] }
```

**Recommendation**: Standardize on RFC 7807 Problem Details.

```json
{
  "type": "https://care.ohc.network/errors/validation-error",
  "title": "Invalid request body",
  "status": 400,
  "detail": "The request body contains invalid fields",
  "instance": "/api/care_radiology/v1/study-reports/",
  "errors": [
    {
      "field": "modality",
      "message": "Invalid UUID format",
      "code": "invalid_uuid"
    }
  ]
}
```

**Implementation**:

```python
from rest_framework.views import exception_handler as drf_exception_handler

def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None:
        response.data = {
            "type": f"https://care.ohc.network/errors/{exc.__class__.__name__}",
            "title": exc.default_detail,
            "status": response.status_code,
            "detail": str(exc),
            "instance": context['request'].path,
            "errors": response.data if isinstance(response.data, list) else None
        }

    return response
```

---

## Database Design Issues

### 9. Missing Encounter Foreign Key

**Severity**: 🟡 **Medium**

**Current State**: `StudyReport` links to `DicomStudy` and `Patient`, but not to `Encounter`.

**Issue**: Reports are not associated with hospital visits/encounters, making it hard to group imaging within a clinical context.

**Recommendation**: Add encounter link (as noted in ARCHITECTURE.md review comment).

```python
class StudyReport(EMRBaseModel):
    study = ForeignKey(DicomStudy, on_delete=CASCADE)
    encounter = ForeignKey(
        'emr.Encounter',
        on_delete=SET_NULL,
        null=True,
        blank=True,
        related_name='radiology_reports'
    )  # NEW

    modality = ForeignKey(ModalityType, on_delete=CASCADE)
    # ... rest of fields
```

**Migration**:

```python
# Backfill existing reports
# Link to encounter based on report created_datetime falling within encounter period
UPDATE radiology_studyreport sr
SET encounter_id = (
    SELECT e.id FROM emr_encounter e
    WHERE e.patient_id = (
        SELECT ds.patient_id FROM radiology_dicomstudy ds
        WHERE ds.id = sr.study_id
    )
    AND sr.created_datetime BETWEEN e.period_start AND e.period_end
    LIMIT 1
)
WHERE sr.encounter_id IS NULL;
```

**FHIR Alignment**: Matches `DiagnosticReport.encounter` in FHIR R4.

---

### 10. No DICOM Metadata Caching in Database

**Severity**: 🟡 **Medium**

**Current State**: `DicomStudy` only stores `dicom_study_uid`. All metadata (study_date, modalities, series count) is fetched from DCM4CHEE on every query.

**Issue**:
- Redis cache can be lost (restart, eviction)
- Cannot query/filter studies by date or modality in SQL
- Performance degrades if DCM4CHEE is slow

**Recommendation**: Cache core DICOM metadata in `DicomStudy` table.

```python
class DicomStudy(EMRBaseModel):
    patient = ForeignKey(Patient, on_delete=CASCADE)
    dicom_study_uid = CharField(max_length=500)

    # NEW: Cached DICOM metadata
    study_date = DateField(null=True, blank=True, db_index=True)
    study_time = TimeField(null=True, blank=True)
    study_datetime = DateTimeField(null=True, blank=True, db_index=True)  # Computed
    study_description = CharField(max_length=255, blank=True)
    accession_number = CharField(max_length=255, blank=True, db_index=True)
    modalities = JSONField(default=list)  # ["CT", "MR"]
    referring_physician = CharField(max_length=255, blank=True)

    # Series/instance counts
    number_of_series = IntegerField(null=True, blank=True)
    number_of_instances = IntegerField(null=True, blank=True)

    # Metadata sync tracking
    metadata_synced_at = DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['patient', 'study_datetime']),
            models.Index(fields=['accession_number']),
        ]
```

**Benefits**:
- SQL queries: `DicomStudy.objects.filter(study_date__gte='2024-01-01', modalities__contains=["CT"])`
- Faster queries (no DCM4CHEE dependency)
- FHIR ImagingStudy resource can be built from DB alone

**Sync Strategy**:

```python
# Update metadata on upload
def update_dicom_metadata(dicom_study):
    study_data = d_query_study(dicom_study.dicom_study_uid)

    dicom_study.study_date = parse_dicom_date(d_find(study_data, "00080020"))
    dicom_study.study_time = parse_dicom_time(d_find(study_data, "00080030"))
    dicom_study.study_description = d_find(study_data, "00081030")[0]
    dicom_study.modalities = d_find(study_data, "00080061")
    dicom_study.number_of_series = count_series(dicom_study.dicom_study_uid)
    dicom_study.metadata_synced_at = timezone.now()
    dicom_study.save()
```

---

### 11. Missing Soft Delete Filters

**Severity**: 🟢 **Low**

**Current State**: `deleted=False` filter must be added to every query manually.

**Issue**: Risk of accidentally querying deleted records.

**Recommendation**: Use custom manager with automatic soft delete filtering.

```python
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted=False)

class DicomStudy(EMRBaseModel):
    # Fields...

    objects = SoftDeleteManager()  # Default manager excludes deleted
    all_objects = models.Manager()  # Access deleted records if needed
```

**Usage**:

```python
# Automatically filters deleted=False
studies = DicomStudy.objects.filter(patient=patient)

# Access deleted records explicitly
deleted_studies = DicomStudy.all_objects.filter(patient=patient, deleted=True)
```

---

### 12. No Database-Level Audit Triggers

**Severity**: 🟢 **Low**

**Current State**: Audit trail (`StudyReportAudit`) is created in Python code.

**Issue**: If code bypasses the viewset (e.g., Django admin, management commands), no audit entry is created.

**Recommendation**: Add PostgreSQL triggers for critical tables.

```sql
-- Trigger function to log all changes to study_report
CREATE OR REPLACE FUNCTION audit_study_report_changes()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO radiology_studyreportaudit (
            study_report_id,
            action,
            field_name,
            old_value,
            new_value,
            created_datetime
        ) VALUES (
            NEW.id,
            'UPDATED',
            'database_trigger',
            row_to_json(OLD),
            row_to_json(NEW),
            NOW()
        );
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO radiology_studyreportaudit (
            study_report_id,
            action,
            field_name,
            old_value,
            new_value,
            created_datetime
        ) VALUES (
            NEW.id,
            'CREATED',
            'database_trigger',
            NULL,
            row_to_json(NEW),
            NOW()
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger to table
CREATE TRIGGER study_report_audit_trigger
AFTER INSERT OR UPDATE ON radiology_studyreport
FOR EACH ROW
EXECUTE FUNCTION audit_study_report_changes();
```

---

## FHIR Compliance Gaps

### 13. Missing ImagingStudy.series Metadata

**Severity**: 🟡 **Medium**

**Current State**: Series metadata is only returned in custom `study_series` array, not in FHIR format.

**Issue**: Cannot generate complete FHIR ImagingStudy resource.

**Recommendation**: Store series metadata or fetch on-demand for FHIR endpoints.

**FHIR ImagingStudy.series Structure**:

```json
{
  "resourceType": "ImagingStudy",
  "id": "...",
  "series": [
    {
      "uid": "1.2.840.113619.2.55.3.2609.2.2.1",
      "number": 1,
      "modality": {
        "system": "http://dicom.nema.org/resources/ontology/DCM",
        "code": "CT"
      },
      "description": "AXIAL",
      "numberOfInstances": 150,
      "bodySite": {
        "system": "http://snomed.info/sct",
        "code": "51185008",
        "display": "Chest"
      },
      "endpoint": [
        {
          "reference": "Endpoint/dicomweb-rs"
        }
      ]
    }
  ]
}
```

**Implementation**: See FHIR endpoint recommendation (#2).

---

### 14. No CodeableConcept for Body Parts/Protocols

**Severity**: 🟢 **Low**

**Current State**: `coding` field is JSONB array but not validated as FHIR CodeableConcept.

**Recommendation**: Use Pydantic models for FHIR coding validation.

```python
from pydantic import BaseModel
from typing import List, Optional

class FHIRCoding(BaseModel):
    system: str  # e.g., "http://snomed.info/sct"
    code: str    # e.g., "51185008"
    display: str # e.g., "Chest"
    version: Optional[str] = None

class FHIRCodeableConcept(BaseModel):
    coding: List[FHIRCoding]
    text: Optional[str] = None

# In BodyPartCreateSpec
class BodyPartCreateSpec(BaseModel):
    modality: UUID
    display_name: str
    coding: List[FHIRCoding]  # Changed from generic list

    def de_serialize(self) -> BodyPart:
        # Validate FHIR codings
        codeable_concept = FHIRCodeableConcept(
            coding=self.coding,
            text=self.display_name
        )

        return BodyPart(
            modality_id=self.modality,
            display_name=self.display_name,
            coding=[c.dict() for c in self.coding]
        )
```

---

### 15. No FHIR Search Parameters

**Severity**: 🟡 **Medium**

**Current State**: Custom query parameters (`?patientId=...`).

**Issue**: Not compatible with FHIR search syntax.

**Recommendation**: Support FHIR search parameters on FHIR endpoints.

```
# FHIR standard search parameters
GET /fhir/ImagingStudy?patient=Patient/550e8400-...
GET /fhir/ImagingStudy?subject=Patient/550e8400-...
GET /fhir/ImagingStudy?started=ge2024-01-01
GET /fhir/ImagingStudy?modality=CT
GET /fhir/ImagingStudy?_lastUpdated=gt2024-03-01

# Chaining
GET /fhir/DiagnosticReport?subject.identifier=MRN|12345
```

**Implementation**: Use `fhir.resources` library for search handling.

---

### 16. Missing FHIR Provenance

**Severity**: 🟢 **Low**

**Current State**: `StudyReportAudit` stores changes but not in FHIR Provenance format.

**Recommendation**: Add FHIR Provenance endpoint for audit trail.

```json
{
  "resourceType": "Provenance",
  "target": [
    { "reference": "DiagnosticReport/a50e8400-..." }
  ],
  "recorded": "2024-03-15T15:00:00Z",
  "agent": [
    {
      "type": {
        "coding": [{
          "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
          "code": "author"
        }]
      },
      "who": {
        "reference": "Practitioner/b50e8400-...",
        "display": "Dr. Jane Smith"
      }
    }
  ],
  "activity": {
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation",
      "code": "UPDATE"
    }]
  },
  "entity": [
    {
      "role": "revision",
      "what": {
        "reference": "DiagnosticReport/a50e8400-..."
      }
    }
  ]
}
```

---

## Security Concerns

### 17. No Rate Limiting

**Severity**: 🟡 **Medium**

**Current State**: No rate limiting on API endpoints.

**Issue**: Vulnerable to DoS attacks, credential stuffing, data scraping.

**Recommendation**: Implement rate limiting.

```python
# settings.py
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'upload': '50/hour',  # Custom rate for upload endpoint
    }
}

# In viewset
class DicomViewSet(ViewSet):
    throttle_classes = [UserRateThrottle]
    throttle_scope = 'upload'  # For upload action
```

---

### 18. Static API Key in Headers

**Severity**: 🔴 **Critical**

**Current State**: Worklist endpoint uses `Authorization: <STATIC_API_KEY>` header.

**Issue**:
- Conflicts with JWT Bearer token header name
- Static key shared across all PACS systems
- No key rotation mechanism
- Key visible in logs/network traces

**Recommendation**: Use separate header and implement key rotation.

```python
# Use custom header
X-API-Key: <STATIC_API_KEY>

# Or use query parameter with HMAC signature
GET /dicom/worklist/?modality=CT&signature=<HMAC-SHA256>

# Better: Use OAuth2 client credentials flow
POST /oauth/token
{
  "grant_type": "client_credentials",
  "client_id": "pacs_system_1",
  "client_secret": "..."
}

# Response
{
  "access_token": "...",
  "expires_in": 3600
}
```

**Implementation**:

```python
class APIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("X-API-Key")

        # Query API key from database (supports multiple keys + rotation)
        try:
            key_obj = APIKey.objects.get(
                key=api_key,
                is_active=True,
                expires_at__gt=timezone.now()
            )
            return (key_obj.user, None)
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid or expired API key")
```

---

### 19. No Field-Level Encryption for PHI

**Severity**: 🟡 **Medium**

**Current State**: PHI stored in plaintext (patient names, findings, impression).

**Issue**: If database is compromised, all PHI is exposed.

**Recommendation**: Encrypt sensitive fields at application layer.

```python
from django_cryptography.fields import encrypt

class StudyReport(EMRBaseModel):
    # ... other fields

    # Encrypt PHI fields
    findings = encrypt(TextField(null=True, blank=True))
    impression = encrypt(TextField(null=True, blank=True))
    technique = encrypt(TextField(null=True, blank=True))
```

**Key Management**: Use AWS KMS, HashiCorp Vault, or django-environ for key storage.

---

### 20. Missing CORS Configuration Documentation

**Severity**: 🟢 **Low**

**Current State**: Nginx handles CORS but no documentation on which origins are allowed.

**Recommendation**: Document CORS policy and add application-level controls.

```python
# settings.py
CORS_ALLOWED_ORIGINS = [
    "https://care.ohc.network",
    "https://ohif.care.ohc.network",
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]
```

---

## Performance Optimizations

### 21. No Database Connection Pooling Documentation

**Severity**: 🟢 **Low**

**Current State**: Database configuration not documented.

**Recommendation**: Document connection pooling settings.

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'dicom',
        'CONN_MAX_AGE': 600,  # 10 minutes
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000'  # 30 seconds
        }
    }
}

# Use pgbouncer for production
DATABASES['default']['HOST'] = 'pgbouncer'
DATABASES['default']['PORT'] = 6432
```

---

### 22. Missing Query Optimization Indexes

**Severity**: 🟡 **Medium**

**Current State**: Basic indexes on foreign keys.

**Issue**: Common queries may be slow without composite indexes.

**Recommendation**: Add composite indexes for common query patterns.

```python
class DicomStudy(EMRBaseModel):
    # ... fields

    class Meta:
        indexes = [
            # Existing
            models.Index(fields=['patient']),
            models.Index(fields=['dicom_study_uid']),

            # NEW: Composite indexes for common queries
            models.Index(fields=['patient', 'created_date']),  # Patient studies by date
            models.Index(fields=['patient', 'deleted']),       # Active studies for patient
            models.Index(fields=['deleted', 'created_date']),  # Recent active studies
        ]

class StudyReport(EMRBaseModel):
    # ... fields

    class Meta:
        indexes = [
            # NEW
            models.Index(fields=['study', 'status', 'deleted']),  # Reports by status
            models.Index(fields=['created_by', 'status']),        # Radiologist workload
            models.Index(fields=['modality', 'created_date']),    # Reports by modality
        ]
```

**Analysis Query**:

```sql
-- Find slow queries
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
WHERE query LIKE '%radiology_%'
ORDER BY mean_time DESC
LIMIT 20;
```

---

### 23. No ETL/Background Job Documentation

**Severity**: 🟢 **Low**

**Current State**: No mention of background jobs for metadata sync, cleanup, etc.

**Recommendation**: Document Celery tasks for async operations.

```python
# tasks.py
from celery import shared_task

@shared_task
def sync_dicom_metadata(study_id):
    """Background task to sync DICOM metadata from DCM4CHEE"""
    study = DicomStudy.objects.get(id=study_id)
    update_dicom_metadata(study)

@shared_task
def cleanup_old_cache_keys():
    """Daily task to cleanup expired cache keys"""
    pattern = "radiology:dicom:study:*"
    # ... cleanup logic

@shared_task
def generate_daily_report_metrics():
    """Daily task to aggregate report statistics"""
    # Count reports by status, modality, radiologist
    # Store in metrics table or send to monitoring system
```

---

### 24. Missing Caching Headers

**Severity**: 🟢 **Low**

**Current State**: No HTTP caching headers in responses.

**Recommendation**: Add Cache-Control headers for appropriate endpoints.

```python
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

class DicomViewSet(ViewSet):

    @method_decorator(cache_page(60 * 60))  # 1 hour
    @action(detail=False, methods=["get"])
    def get_studies(self, request):
        # ... existing logic

        response = Response(results)

        # Add caching headers
        response['Cache-Control'] = 'private, max-age=3600'
        response['Vary'] = 'Authorization'

        return response
```

---

## API Versioning

### 25. No Deprecation Policy

**Severity**: 🟡 **Medium**

**Current State**: No documented API lifecycle or deprecation process.

**Recommendation**: Define versioning and deprecation policy.

```markdown
## API Versioning Policy

### Supported Versions
- **v1**: Current stable version (2024-01-01 to 2025-12-31)
- **v2**: Beta (2024-06-01 onwards)

### Deprecation Timeline
1. **6 months notice**: Deprecation announced in API changelog
2. **Warning headers**: `Sunset: Sat, 31 Dec 2025 23:59:59 GMT`
3. **HTTP 410 Gone**: After sunset date

### Breaking Changes
Breaking changes require a new major version:
- Removing fields from responses
- Changing field types
- Renaming endpoints
- Changing authentication methods

### Non-Breaking Changes
Can be added to existing version:
- Adding new fields to responses
- Adding new endpoints
- Adding optional request parameters
```

**Implementation**:

```python
class DeprecatedEndpointMixin:
    sunset_date = None  # e.g., "2025-12-31"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)

        if self.sunset_date:
            response['Sunset'] = self.sunset_date
            response['Deprecation'] = 'true'
            response['Link'] = '</api/v2/endpoint>; rel="successor-version"'

        return response
```

---

### 26. No OpenAPI/Swagger Documentation

**Severity**: 🟡 **Medium**

**Current State**: Only markdown documentation.

**Issue**: No interactive API explorer, harder for developers to test endpoints.

**Recommendation**: Add OpenAPI (Swagger) documentation.

```python
# Install drf-spectacular
# pip install drf-spectacular

# settings.py
INSTALLED_APPS += ['drf_spectacular']

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Care Radiology API',
    'DESCRIPTION': 'DICOM imaging management for Care EMR',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/care_radiology/v1/',
}

# urls.py
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

**Access**: Visit `http://localhost:9000/api/care_radiology/v1/docs/` for interactive docs.

---

## Documentation Improvements

### 27. Missing Webhook Documentation

**Severity**: 🟢 **Low**

**Current State**: `RadiologyWebhookLogs` model exists but no webhook endpoint documented.

**Recommendation**: Document webhook endpoint if it exists, or remove the model if unused.

```markdown
## Webhook Endpoint

### Receive DCM4CHEE Study Events

**Endpoint**: `POST /api/care_radiology/v1/webhooks/dcm4chee/`

**Purpose**: Receive notifications from DCM4CHEE when studies are stored.

**Authentication**: Static API Key (X-Webhook-Secret header)

**Request**:
```json
{
  "eventType": "STUDY_RECEIVED",
  "studyInstanceUID": "1.2.840.113619...",
  "patientID": "MRN12345",
  "timestamp": "2024-03-15T14:30:00Z"
}
```

**Response**: `200 OK`
```

---

### 28. No Error Code Reference

**Severity**: 🟢 **Low**

**Recommendation**: Add error code catalog.

```markdown
## Error Codes

| Code | HTTP | Description | Resolution |
|------|------|-------------|------------|
| `INVALID_PATIENT_ID` | 400 | Patient UUID not found | Check patient external_id |
| `INVALID_STUDY_UID` | 400 | DICOM study UID not found | Verify study exists in DCM4CHEE |
| `PERMISSION_DENIED_PATIENT` | 403 | No access to patient | Request access from admin |
| `PERMISSION_DENIED_REPORT` | 403 | No radiology report permission | Requires radiologist role |
| `DCM4CHEE_UNAVAILABLE` | 502 | PACS system unreachable | Contact DevOps |
| `REPORT_ALREADY_FINAL` | 409 | Cannot modify final report | Create amendment instead |
```

---

### 29. Missing Performance SLAs

**Severity**: 🟢 **Low**

**Recommendation**: Document expected response times.

```markdown
## Performance SLAs

| Endpoint | p50 | p95 | p99 | Notes |
|----------|-----|-----|-----|-------|
| POST /dicom/upload/ | 2s | 5s | 10s | Depends on file size |
| GET /dicom/studies/ (cached) | 100ms | 200ms | 500ms | Redis cache hit |
| GET /dicom/studies/ (uncached) | 1s | 2s | 5s | DCM4CHEE queries |
| POST /study-reports/ | 200ms | 500ms | 1s | Database insert |
| GET /study-report-audits/ | 100ms | 300ms | 800ms | Index scan |
```

---

### 30. No Client SDK Examples

**Severity**: 🟢 **Low**

**Recommendation**: Add SDK examples for common languages.

```typescript
// TypeScript/JavaScript SDK example
import { CareRadiologyClient } from '@care/radiology-sdk';

const client = new CareRadiologyClient({
  baseURL: 'https://care.ohc.network/api/care_radiology/v1',
  token: 'Bearer ...'
});

// Upload DICOM
const uploadResult = await client.uploadDICOM({
  patientId: '550e8400-...',
  file: dicomFile
});

// Create report
const report = await client.createReport({
  studyId: '650e8400-...',
  modalityId: '750e8400-...',
  bodyPartId: '850e8400-...',
  scanProtocolId: '950e8400-...',
  findings: 'No acute abnormality',
  impression: 'Normal study'
});
```

---

## Implementation Priority Matrix

### Priority 0 (Critical - Next Sprint)

| # | Issue | Effort | Impact | Risk if Not Fixed |
|---|-------|--------|--------|-------------------|
| 2 | FHIR Endpoints | High | High | Cannot integrate with HIE systems |
| 3 | Report Status Workflow | Medium | Critical | Clinical safety - cannot track report validity |
| 18 | Fix Static API Key | Low | High | Security vulnerability |

**Estimated Effort**: 2-3 sprints

---

### Priority 1 (High - Next Quarter)

| # | Issue | Effort | Impact | Risk if Not Fixed |
|---|-------|--------|--------|-------------------|
| 1 | API Versioning | Medium | High | Cannot make breaking changes |
| 4 | REST Naming Consistency | Low | Medium | Developer confusion |
| 5 | Pagination Config | Low | Medium | Performance issues at scale |
| 8 | Error Response Format | Low | Medium | Inconsistent client error handling |
| 9 | Encounter Foreign Key | Low | Medium | Missing clinical context |
| 10 | DICOM Metadata Caching | Medium | High | Poor query performance |
| 15 | FHIR Search Parameters | High | Medium | FHIR compliance |
| 17 | Rate Limiting | Low | High | DoS vulnerability |
| 22 | Query Optimization | Medium | High | Slow queries at scale |

**Estimated Effort**: 1 quarter

---

### Priority 2 (Medium - Backlog)

| # | Issue | Effort | Impact |
|---|-------|--------|--------|
| 6 | Bulk Operations | Medium | Low |
| 7 | HATEOAS Links | Low | Low |
| 11 | Soft Delete Manager | Low | Low |
| 12 | DB Audit Triggers | Medium | Low |
| 13 | ImagingStudy Series | Medium | Medium |
| 14 | FHIR CodeableConcept | Low | Low |
| 16 | FHIR Provenance | Medium | Low |
| 19 | Field Encryption | High | Medium |
| 20 | CORS Documentation | Low | Low |
| 21 | Connection Pooling Docs | Low | Low |
| 23 | Background Jobs Docs | Medium | Low |
| 24 | Caching Headers | Low | Low |
| 25 | Deprecation Policy | Low | Low |
| 26 | OpenAPI/Swagger | Medium | Medium |
| 27 | Webhook Documentation | Low | Low |
| 28 | Error Code Reference | Low | Low |
| 29 | Performance SLAs | Low | Low |
| 30 | Client SDK Examples | High | Medium |

**Estimated Effort**: Ongoing

---

## Summary

### Key Recommendations

**Immediate Actions (P0)**:
1. ✅ Add report status workflow (draft → final) for clinical safety
2. ✅ Implement FHIR endpoints for healthcare interoperability
3. ✅ Fix static API key security issue

**Short-term (P1)**:
1. ✅ Add API versioning (`/v1/` prefix)
2. ✅ Cache DICOM metadata in database
3. ✅ Implement rate limiting
4. ✅ Add encounter foreign key

**Long-term (P2)**:
1. ✅ OpenAPI/Swagger documentation
2. ✅ Field-level encryption for PHI
3. ✅ Client SDKs for common languages

### FHIR Compliance Roadmap

Follow the 5-phase plan in [FHIR_ANALYSIS.md](./FHIR_ANALYSIS.md):
- **Phase 1**: Foundation (FHIR API endpoints, basic mappings)
- **Phase 2**: Data model enhancements (status, encounter, metadata)
- **Phase 3**: Terminology integration (ValueSets, CodeSystems)
- **Phase 4**: Structured findings (Observation resources)
- **Phase 5**: Full compliance (search parameters, SMART-on-FHIR)

---

**Review Document Version**: 1.0
**Next Review Date**: 2026-07-23
**Document Owner**: Care Radiology Technical Team
