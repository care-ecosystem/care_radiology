# FHIR Analysis - Care Radiology Plugin

## Executive Summary

This document provides a comprehensive analysis of the care_radiology plugin's data models and storage architecture in relation to **FHIR (Fast Healthcare Interoperability Resources)** R4/R5 standards. It includes mappings, gap analysis, and recommendations for achieving FHIR compliance and healthcare interoperability.

**Document Version**: 1.0
**FHIR Version**: R4 (with R5 notes)
**Last Updated**: 2026-04-22

---

## Table of Contents

1. [FHIR Overview](#fhir-overview)
2. [Model-to-FHIR Resource Mapping](#model-to-fhir-resource-mapping)
3. [Detailed Resource Analysis](#detailed-resource-analysis)
4. [DICOM and FHIR Integration](#dicom-and-fhir-integration)
5. [Gap Analysis](#gap-analysis)
6. [FHIR Implementation Roadmap](#fhir-implementation-roadmap)
7. [Example FHIR Resources](#example-fhir-resources)
8. [Recommendations](#recommendations)

---

## FHIR Overview

### What is FHIR?

**FHIR** (Fast Healthcare Interoperability Resources) is a healthcare data exchange standard developed by HL7. It defines:
- Standard data models (Resources)
- RESTful API patterns
- Interoperability between healthcare systems
- Support for various data formats (JSON, XML)

### FHIR in Radiology Context

Key FHIR resources for radiology workflows:
- **ImagingStudy**: Represents a DICOM study
- **DiagnosticReport**: Radiology report with findings/impression
- **ServiceRequest**: Order for imaging procedure
- **Observation**: Individual findings or measurements
- **DocumentReference**: Attached reports, images
- **Endpoint**: DICOM server endpoints (WADO, QIDO, STOW)

---

## Model-to-FHIR Resource Mapping

### High-Level Mapping Table

| care_radiology Model | FHIR Resource(s) | Match Quality | Notes |
|---------------------|------------------|---------------|-------|
| **DicomStudy** | `ImagingStudy` | ✅ Excellent | Direct 1:1 mapping |
| **StudyReport** | `DiagnosticReport` | ✅ Excellent | Core radiology report resource |
| **StudyReportAudit** | `Provenance` | ✅ Good | Audit trail tracking |
| **RadiologyServiceRequest** | `ServiceRequest` | ✅ Excellent | Order/requisition |
| **ModalityType** | `CodeableConcept` | ⚠️ Partial | Use DICOM/SNOMED codes |
| **BodyPart** | `CodeableConcept` | ⚠️ Partial | Use SNOMED anatomy codes |
| **ScanProtocol** | `CodeableConcept` + `PlanDefinition` | ⚠️ Partial | Protocol definition |
| **Template** | `Questionnaire` or `ActivityDefinition` | ⚠️ Partial | Report template structure |
| **RadiologyWebhookLogs** | `AuditEvent` | ✅ Good | System audit logging |

**Legend**:
- ✅ Excellent: Direct mapping, standard FHIR resource
- ⚠️ Partial: Can be represented, but requires transformation
- ❌ Poor: No direct FHIR equivalent

---

## Detailed Resource Analysis

### 1. DicomStudy → ImagingStudy

**care_radiology Model**:
```python
class DicomStudy(EMRBaseModel):
    patient = ForeignKey("emr.Patient")
    dicom_study_uid = CharField(max_length=500)
```

**FHIR ImagingStudy Resource**:
```json
{
  "resourceType": "ImagingStudy",
  "id": "dicom-study-uuid",
  "identifier": [{
    "system": "urn:dicom:uid",
    "value": "urn:oid:1.2.840.113619.2.55.3.2609.2.1.1"
  }],
  "status": "available",
  "subject": {
    "reference": "Patient/patient-uuid",
    "display": "John Doe"
  },
  "started": "2025-04-16T10:30:00Z",
  "numberOfSeries": 2,
  "numberOfInstances": 150,
  "modality": [{
    "system": "http://dicom.nema.org/resources/ontology/DCM",
    "code": "CT",
    "display": "Computed Tomography"
  }],
  "description": "CT Brain without Contrast",
  "series": [{
    "uid": "1.2.840.113619.2.55.3.2609.2.2.1",
    "number": 1,
    "modality": {
      "system": "http://dicom.nema.org/resources/ontology/DCM",
      "code": "CT"
    },
    "description": "Axial Brain",
    "numberOfInstances": 150,
    "bodySite": {
      "system": "http://snomed.info/sct",
      "code": "12738006",
      "display": "Brain structure"
    },
    "endpoint": [{
      "reference": "Endpoint/dicomweb-endpoint"
    }],
    "instance": [{
      "uid": "1.2.840.113619.2.55.3.2609.2.3.1",
      "sopClass": {
        "system": "urn:ietf:rfc:3986",
        "code": "urn:oid:1.2.840.10008.5.1.4.1.1.2"
      },
      "number": 1
    }]
  }]
}
```

**Mapping Analysis**:

| care_radiology Field | FHIR ImagingStudy Field | Status | Notes |
|---------------------|------------------------|--------|-------|
| `dicom_study_uid` | `identifier[0].value` | ✅ Direct | Use urn:oid: prefix |
| `patient` | `subject` | ✅ Direct | Reference to Patient resource |
| `created_date` | `started` | ⚠️ Approximation | Use study date from DICOM |
| (from DCM4CHEE) | `series[]` | ⚠️ External | Query from PACS |
| (from DCM4CHEE) | `numberOfSeries` | ⚠️ External | Query from PACS |
| (from DCM4CHEE) | `modality` | ⚠️ External | Parse from DICOM tags |

**Gaps**:
- ❌ Series-level metadata not stored in care_radiology
- ❌ Study date/time from DICOM not persisted
- ❌ Modality information not stored (retrieved from DCM4CHEE)
- ⚠️ No endpoint reference to DICOM server

**Recommendation**: Enhance DicomStudy model to cache key DICOM metadata:
```python
class DicomStudy(EMRBaseModel):
    patient = ForeignKey("emr.Patient")
    dicom_study_uid = CharField(max_length=500)

    # NEW: Cache DICOM metadata
    study_date = DateField(null=True)
    study_time = TimeField(null=True)
    study_description = CharField(max_length=255, blank=True)
    modalities = JSONField(default=list)  # ["CT", "MR"]
    number_of_series = IntegerField(null=True)
    number_of_instances = IntegerField(null=True)
    referring_physician = CharField(max_length=255, blank=True)
    accession_number = CharField(max_length=255, blank=True)
```

---

### 2. StudyReport → DiagnosticReport

**care_radiology Model**:
```python
class StudyReport(EMRBaseModel):
    study = ForeignKey(DicomStudy)
    modality = ForeignKey(ModalityType)
    body_part = ForeignKey(BodyPart)
    scan_protocol = ForeignKey(ScanProtocol)
    technique = TextField()
    findings = TextField()
    impression = TextField()
    created_datetime = DateTimeField()
    last_modified_datetime = DateTimeField()
```

**FHIR DiagnosticReport Resource**:
```json
{
  "resourceType": "DiagnosticReport",
  "id": "study-report-uuid",
  "identifier": [{
    "system": "https://care.ohc.network/fhir/study-report",
    "value": "study-report-uuid"
  }],
  "basedOn": [{
    "reference": "ServiceRequest/service-request-uuid",
    "display": "CT Brain Order"
  }],
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
      "code": "RAD",
      "display": "Radiology"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "18748-4",
      "display": "Diagnostic imaging study"
    }],
    "text": "CT Brain without Contrast"
  },
  "subject": {
    "reference": "Patient/patient-uuid"
  },
  "encounter": {
    "reference": "Encounter/encounter-uuid"
  },
  "effectiveDateTime": "2025-04-16T10:30:00Z",
  "issued": "2025-04-16T14:30:00Z",
  "performer": [{
    "reference": "Practitioner/radiologist-uuid",
    "display": "Dr. Smith, Radiologist"
  }],
  "resultsInterpreter": [{
    "reference": "Practitioner/radiologist-uuid"
  }],
  "imagingStudy": [{
    "reference": "ImagingStudy/dicom-study-uuid"
  }],
  "conclusion": "Normal CT brain. No acute intracranial abnormality.",
  "conclusionCode": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "281900007",
      "display": "No abnormality detected"
    }]
  }],
  "presentedForm": [{
    "contentType": "text/plain",
    "language": "en-US",
    "data": "VGVjaG5pcXVlOi4uLg==",
    "title": "Radiology Report",
    "creation": "2025-04-16T14:30:00Z"
  }]
}
```

**Mapping Analysis**:

| care_radiology Field | FHIR DiagnosticReport Field | Status | Notes |
|---------------------|----------------------------|--------|-------|
| `study` | `imagingStudy[0]` | ✅ Direct | Reference to ImagingStudy |
| `impression` | `conclusion` | ✅ Direct | Main report conclusion |
| `created_datetime` | `issued` | ✅ Direct | When report finalized |
| `created_by` | `performer[0]` | ✅ Direct | Reporting radiologist |
| `modality` | `code.coding` | ⚠️ Partial | Map to LOINC procedure codes |
| `body_part` | `code.coding` | ⚠️ Partial | Include in procedure code |
| `technique` | `presentedForm.data` | ⚠️ Partial | Include in formatted report |
| `findings` | `presentedForm.data` | ⚠️ Partial | Include in formatted report |
| N/A | `basedOn` | ❌ Missing | No direct link to ServiceRequest |
| N/A | `encounter` | ❌ Missing | No encounter context |
| N/A | `status` | ⚠️ Implied | Always "final" |

**Gaps**:
- ❌ No structured findings (should use `Observation` resources)
- ❌ No link to originating ServiceRequest
- ❌ No encounter context
- ❌ No report status workflow (draft, preliminary, final, amended)
- ❌ No coded conclusions (SNOMED CT findings)

**Recommendation**: Enhance StudyReport model:
```python
class StudyReport(EMRBaseModel):
    study = ForeignKey(DicomStudy)
    encounter = ForeignKey("emr.Encounter", null=True)  # NEW
    service_request = ForeignKey("emr.ServiceRequest", null=True)  # NEW

    status = CharField(  # NEW
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("preliminary", "Preliminary"),
            ("final", "Final"),
            ("amended", "Amended"),
            ("corrected", "Corrected"),
            ("cancelled", "Cancelled")
        ],
        default="draft"
    )

    modality = ForeignKey(ModalityType)
    body_part = ForeignKey(BodyPart)
    scan_protocol = ForeignKey(ScanProtocol)

    technique = TextField()
    findings = TextField()
    impression = TextField()

    # NEW: Coded conclusions
    conclusion_codes = JSONField(default=list)  # SNOMED CT codes

    # NEW: Timestamps
    study_datetime = DateTimeField()  # When study performed
    reported_datetime = DateTimeField()  # When report issued
    verified_datetime = DateTimeField(null=True)  # When verified

    created_datetime = DateTimeField()
    last_modified_datetime = DateTimeField()
```

---

### 3. StudyReportAudit → Provenance

**care_radiology Model**:
```python
class StudyReportAudit(EMRBaseModel):
    study_report = ForeignKey(StudyReport)
    action = CharField(max_length=20)  # CREATED, UPDATED
    field_name = CharField(max_length=100)
    old_value = JSONField(null=True)
    new_value = JSONField(null=True)
    created_datetime = DateTimeField()
```

**FHIR Provenance Resource**:
```json
{
  "resourceType": "Provenance",
  "id": "audit-uuid",
  "target": [{
    "reference": "DiagnosticReport/study-report-uuid"
  }],
  "occurredDateTime": "2025-04-16T14:30:00Z",
  "recorded": "2025-04-16T14:30:01Z",
  "activity": {
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v3-DataOperation",
      "code": "UPDATE",
      "display": "revise"
    }]
  },
  "agent": [{
    "type": {
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
        "code": "author",
        "display": "Author"
      }]
    },
    "who": {
      "reference": "Practitioner/radiologist-uuid",
      "display": "Dr. Smith"
    }
  }],
  "entity": [{
    "role": "revision",
    "what": {
      "reference": "DiagnosticReport/study-report-uuid/_history/1"
    }
  }]
}
```

**Mapping Analysis**:

| care_radiology Field | FHIR Provenance Field | Status | Notes |
|---------------------|----------------------|--------|-------|
| `study_report` | `target[0]` | ✅ Direct | What was modified |
| `created_datetime` | `occurredDateTime` | ✅ Direct | When change occurred |
| `created_by` | `agent[0].who` | ✅ Direct | Who made change |
| `action` | `activity.coding` | ✅ Direct | CREATE, UPDATE, DELETE |
| `field_name` | N/A | ⚠️ Custom | Store in extension |
| `old_value` | `entity[0].what` | ⚠️ Partial | Reference to previous version |
| `new_value` | N/A | ⚠️ Current | Implicitly current version |

**Recommendation**: FHIR-compliant audit trail implementation:
```python
# Use FHIR Provenance for audit trail
# Store field-level changes in FHIR extension
```

---

### 4. RadiologyServiceRequest → ServiceRequest

**care_radiology Model**:
```python
class RadiologyServiceRequest(EMRBaseModel):
    service_request = ForeignKey("emr.ServiceRequest")
    dicom_study = ForeignKey(DicomStudy, null=True)
    raw_data = JSONField()
```

**FHIR ServiceRequest Resource**:
```json
{
  "resourceType": "ServiceRequest",
  "id": "service-request-uuid",
  "identifier": [{
    "system": "https://care.ohc.network/fhir/service-request",
    "value": "service-request-uuid"
  }],
  "status": "completed",
  "intent": "order",
  "category": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "363679005",
      "display": "Imaging"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "24727-0",
      "display": "CT Head W/O Contrast"
    }],
    "text": "CT Brain without Contrast"
  },
  "subject": {
    "reference": "Patient/patient-uuid"
  },
  "encounter": {
    "reference": "Encounter/encounter-uuid"
  },
  "occurrenceDateTime": "2025-04-16T10:00:00Z",
  "authoredOn": "2025-04-15T14:00:00Z",
  "requester": {
    "reference": "Practitioner/referring-physician-uuid",
    "display": "Dr. Johnson"
  },
  "performer": [{
    "reference": "Practitioner/radiologist-uuid"
  }],
  "reasonCode": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "25064002",
      "display": "Headache"
    }],
    "text": "Persistent headache, rule out mass"
  }],
  "supportingInfo": [{
    "reference": "ImagingStudy/dicom-study-uuid"
  }]
}
```

**Mapping Analysis**:

| care_radiology Field | FHIR ServiceRequest Field | Status | Notes |
|---------------------|--------------------------|--------|-------|
| `service_request` | Inherits from CARE | ✅ Assumed | CARE manages base ServiceRequest |
| `dicom_study` | `supportingInfo[0]` | ✅ Direct | Link to completed imaging |
| `raw_data` | N/A | ⚠️ Internal | Webhook metadata |

**Note**: CARE already manages ServiceRequest as FHIR resource. The RadiologyServiceRequest model just links it to DicomStudy.

**Recommendation**:
- Ensure CARE's ServiceRequest model follows FHIR R4 spec
- Use `supportingInfo` to reference completed ImagingStudy
- Update status workflow: requested → scheduled → in-progress → completed

---

### 5. ModalityType, BodyPart, ScanProtocol → CodeableConcept

**care_radiology Models** (Configuration):
```python
class ModalityType(EMRBaseModel):
    display_name = CharField(max_length=255)
    coding = JSONField(default=list)

class BodyPart(EMRBaseModel):
    modality = ForeignKey(ModalityType)
    display_name = CharField(max_length=255)
    coding = JSONField(default=list)

class ScanProtocol(EMRBaseModel):
    modality = ForeignKey(ModalityType)
    body_part = ForeignKey(BodyPart)
    display_name = CharField(max_length=255)
    coding = JSONField(default=list)
```

**FHIR Representation**:

These should use standard **CodeableConcept** with terminology bindings:

```json
{
  "modality": {
    "coding": [{
      "system": "http://dicom.nema.org/resources/ontology/DCM",
      "code": "CT",
      "display": "Computed Tomography"
    }]
  },
  "bodySite": {
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "12738006",
      "display": "Brain structure"
    }]
  },
  "procedure": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "24727-0",
      "display": "CT Head W/O Contrast"
    }, {
      "system": "http://www.ama-assn.org/go/cpt",
      "code": "70450",
      "display": "CT head/brain without contrast"
    }]
  }
}
```

**Standard Code Systems**:

| Type | Code System | Example |
|------|-------------|---------|
| **Modality** | DICOM DCM | CT, MR, CR, DX, US, NM |
| **Body Part** | SNOMED CT | 12738006 (Brain), 51185008 (Chest) |
| **Procedure** | LOINC | 24727-0 (CT Head W/O Contrast) |
| **Procedure** | CPT | 70450 (CT head/brain without contrast) |

**Mapping Analysis**:

| Current Approach | FHIR Best Practice | Status |
|-----------------|-------------------|--------|
| Database tables for types | Use ValueSet resources | ⚠️ Over-engineered |
| Custom coding JSON | Use standard terminologies | ⚠️ Partial |
| Hierarchical FK relationships | Use CodeSystem hierarchy | ⚠️ Different model |

**Gaps**:
- ⚠️ Database tables for what should be coded values
- ⚠️ Not using standard FHIR ValueSet resources
- ⚠️ Reinventing terminology management

**Recommendation**:

**Option A - Simplify (Recommended)**:
```python
# Remove ModalityType, BodyPart, ScanProtocol models
# Use FHIR ValueSet resources + terminology server

# In StudyReport:
class StudyReport(EMRBaseModel):
    study = ForeignKey(DicomStudy)

    # Use standard codes directly
    modality_code = JSONField()  # DICOM DCM codes
    body_site_code = JSONField()  # SNOMED CT codes
    procedure_code = JSONField()  # LOINC + CPT codes

    technique = TextField()
    findings = TextField()
    impression = TextField()
```

**Option B - Keep for UI/UX**:
```python
# Keep models but populate from FHIR ValueSets
# Use as cache for dropdown lists
# Sync periodically with terminology server
```

**FHIR ValueSet Example**:
```json
{
  "resourceType": "ValueSet",
  "id": "radiology-modalities",
  "url": "https://care.ohc.network/fhir/ValueSet/radiology-modalities",
  "version": "1.0.0",
  "name": "RadiologyModalities",
  "status": "active",
  "compose": {
    "include": [{
      "system": "http://dicom.nema.org/resources/ontology/DCM",
      "concept": [
        {"code": "CT", "display": "Computed Tomography"},
        {"code": "MR", "display": "Magnetic Resonance"},
        {"code": "CR", "display": "Computed Radiography"},
        {"code": "DX", "display": "Digital Radiography"},
        {"code": "US", "display": "Ultrasound"},
        {"code": "NM", "display": "Nuclear Medicine"},
        {"code": "PT", "display": "Positron emission tomography"},
        {"code": "MG", "display": "Mammography"}
      ]
    }]
  }
}
```

---

### 6. Template → Questionnaire (or ActivityDefinition)

**care_radiology Model**:
```python
class Template(EMRBaseModel):
    user = ForeignKey(User)
    modality = ForeignKey(ModalityType)
    body_part = ForeignKey(BodyPart)
    scan_protocol = ForeignKey(ScanProtocol)
    technique = TextField()
    findings = TextField()
    impression = TextField()
```

**FHIR Questionnaire Resource**:
```json
{
  "resourceType": "Questionnaire",
  "id": "ct-brain-report-template",
  "url": "https://care.ohc.network/fhir/Questionnaire/ct-brain-report-template",
  "version": "1.0",
  "name": "CTBrainReportTemplate",
  "title": "CT Brain Report Template",
  "status": "active",
  "subjectType": ["Patient"],
  "item": [{
    "linkId": "technique",
    "text": "Technique",
    "type": "text",
    "required": false,
    "initial": [{
      "valueString": "Non-contrast CT brain performed with 5mm axial slices..."
    }]
  }, {
    "linkId": "findings",
    "text": "Findings",
    "type": "text",
    "required": true,
    "initial": [{
      "valueString": "The brain parenchyma demonstrates normal attenuation..."
    }]
  }, {
    "linkId": "impression",
    "text": "Impression",
    "type": "text",
    "required": true,
    "initial": [{
      "valueString": "Normal CT brain."
    }]
  }]
}
```

**Alternative: ActivityDefinition** (For protocol definitions):
```json
{
  "resourceType": "ActivityDefinition",
  "id": "ct-brain-protocol",
  "url": "https://care.ohc.network/fhir/ActivityDefinition/ct-brain-protocol",
  "version": "1.0",
  "name": "CTBrainProtocol",
  "title": "CT Brain Imaging Protocol",
  "status": "active",
  "kind": "ImagingStudy",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "24727-0",
      "display": "CT Head W/O Contrast"
    }]
  },
  "bodySite": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "12738006",
      "display": "Brain structure"
    }]
  }],
  "description": "Standard protocol for CT brain without contrast"
}
```

**Recommendation**:
- Use `Questionnaire` for report templates (what radiologist fills out)
- Use `ActivityDefinition` for imaging protocols (how study is performed)
- Store both as FHIR resources in database or external terminology server

---

### 7. RadiologyWebhookLogs → AuditEvent

**care_radiology Model**:
```python
class RadiologyWebhookLogs(EMRBaseModel):
    raw_data = JSONField()
    type = CharField(max_length=50)
```

**FHIR AuditEvent Resource**:
```json
{
  "resourceType": "AuditEvent",
  "id": "webhook-log-uuid",
  "type": {
    "system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
    "code": "rest",
    "display": "RESTful Operation"
  },
  "subtype": [{
    "system": "http://hl7.org/fhir/restful-interaction",
    "code": "create",
    "display": "create"
  }],
  "action": "C",
  "recorded": "2025-04-16T10:30:00Z",
  "outcome": "0",
  "agent": [{
    "type": {
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/extra-security-role-type",
        "code": "datacollector",
        "display": "Data Collector"
      }]
    },
    "who": {
      "display": "DCM4CHEE Archive"
    },
    "requestor": false,
    "network": {
      "address": "192.168.1.100",
      "type": "1"
    }
  }],
  "source": {
    "site": "DCM4CHEE",
    "observer": {
      "display": "DCM4CHEE Archive"
    },
    "type": [{
      "system": "http://terminology.hl7.org/CodeSystem/security-source-type",
      "code": "4",
      "display": "Application Server"
    }]
  },
  "entity": [{
    "what": {
      "reference": "ImagingStudy/dicom-study-uuid"
    },
    "type": {
      "system": "http://terminology.hl7.org/CodeSystem/audit-entity-type",
      "code": "2",
      "display": "System Object"
    },
    "role": {
      "system": "http://terminology.hl7.org/CodeSystem/object-role",
      "code": "3",
      "display": "Report"
    }
  }]
}
```

**Recommendation**:
- Map webhook events to FHIR AuditEvent resources
- Store raw webhook data in `entity.detail` extension
- Enable FHIR-based audit log queries

---

## DICOM and FHIR Integration

### ImagingStudy + Endpoint Pattern

**FHIR Endpoint Resource** (DICOM Server):
```json
{
  "resourceType": "Endpoint",
  "id": "dcm4chee-dicomweb",
  "status": "active",
  "connectionType": {
    "system": "http://terminology.hl7.org/CodeSystem/endpoint-connection-type",
    "code": "dicom-wado-rs",
    "display": "DICOM WADO-RS"
  },
  "name": "DCM4CHEE DICOMweb Endpoint",
  "address": "http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs",
  "payloadType": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/endpoint-payload-type",
      "code": "DICOM",
      "display": "DICOM"
    }]
  }],
  "header": [
    "Accept: application/dicom+json"
  ]
}
```

**ImagingStudy References Endpoint**:
```json
{
  "resourceType": "ImagingStudy",
  "series": [{
    "endpoint": [{
      "reference": "Endpoint/dcm4chee-dicomweb"
    }]
  }]
}
```

**Benefit**: Clients can discover DICOMweb endpoints dynamically

**Recommendation**: Create Endpoint resource for DCM4CHEE configuration

---

### FHIR ImagingStudy with DICOMweb Links

**ImagingStudy with WADO-RS URLs**:
```json
{
  "resourceType": "ImagingStudy",
  "series": [{
    "uid": "1.2.840.113619.2.55.3.2609.2.2.1",
    "instance": [{
      "uid": "1.2.840.113619.2.55.3.2609.2.3.1",
      "sopClass": {
        "system": "urn:ietf:rfc:3986",
        "code": "urn:oid:1.2.840.10008.5.1.4.1.1.2"
      },
      "number": 1,
      "_url": {
        "extension": [{
          "url": "http://hl7.org/fhir/StructureDefinition/instance-url",
          "valueUri": "http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.2.840.../series/1.2.840.../instances/1.2.840..."
        }]
      }
    }]
  }]
}
```

**OHIF Integration**:
```javascript
// OHIF can consume FHIR ImagingStudy resource directly
fetch('/api/fhir/ImagingStudy?patient=<patient-id>')
  .then(r => r.json())
  .then(bundle => {
    // Load studies into OHIF viewer
    const studies = bundle.entry.map(e => e.resource);
    OHIF.loadStudies(studies);
  });
```

---

## Gap Analysis

### Critical Gaps

| Gap | Impact | Priority | Mitigation |
|-----|--------|----------|------------|
| **No FHIR API endpoint** | Cannot integrate with FHIR clients | 🔴 High | Implement FHIR REST API |
| **No Encounter link in reports** | Missing clinical context | 🔴 High | Add encounter FK to StudyReport |
| **No report status workflow** | Can't track draft/final/amended | 🔴 High | Add status field |
| **Configuration as DB tables** | Not using standard terminologies | 🟡 Medium | Use ValueSet resources |
| **No structured findings** | Findings only in free text | 🟡 Medium | Add Observation resources |
| **No DICOM metadata cached** | ImagingStudy incomplete | 🟡 Medium | Cache key DICOM tags |
| **No Endpoint resource** | Can't discover DICOMweb endpoints | 🟢 Low | Create Endpoint resource |

### Interoperability Gaps

| Capability | Current State | FHIR Standard | Gap |
|-----------|---------------|---------------|-----|
| **Query radiology reports** | Custom REST API | FHIR search parameters | ⚠️ Different API |
| **Export report to external system** | No standard format | DiagnosticReport resource | ❌ Not supported |
| **Import report from external system** | Webhook only | FHIR create/update | ⚠️ Limited |
| **Link to orders** | Via RadiologyServiceRequest | ServiceRequest.supportingInfo | ⚠️ Indirect |
| **Standardized codes** | Custom tables | FHIR ValueSet/CodeSystem | ⚠️ Non-standard |

---

## FHIR Implementation Roadmap

### Phase 1: Foundation (Immediate - 2 weeks)

**Goals**: Establish FHIR resource mappings and basic API

**Tasks**:
1. ✅ Define FHIR resource mappings (this document)
2. ⏳ Install FHIR server library (django-fhir or hapi-fhir-jpaserver)
3. ⏳ Create FHIR REST API endpoints:
   - `GET /fhir/ImagingStudy?patient=<id>`
   - `GET /fhir/DiagnosticReport?patient=<id>`
   - `GET /fhir/ServiceRequest?patient=<id>`
4. ⏳ Implement resource serializers (model → FHIR JSON)
5. ⏳ Add FHIR content negotiation (`Accept: application/fhir+json`)

**Deliverables**:
- Basic FHIR read-only API
- Documentation for FHIR endpoints

---

### Phase 2: Data Model Enhancements (1-2 weeks)

**Goals**: Align data models with FHIR resources

**Tasks**:
1. ⏳ Enhance DicomStudy model:
   ```python
   study_date = DateField()
   study_time = TimeField()
   modalities = JSONField()
   accession_number = CharField()
   ```
2. ⏳ Enhance StudyReport model:
   ```python
   status = CharField(choices=REPORT_STATUS_CHOICES)
   encounter = ForeignKey("emr.Encounter")
   service_request = ForeignKey("emr.ServiceRequest")
   conclusion_codes = JSONField()  # SNOMED CT
   ```
3. ⏳ Add migration scripts
4. ⏳ Update API endpoints to populate new fields

**Deliverables**:
- Enhanced data models
- Migration scripts
- Updated API endpoints

---

### Phase 3: Terminology Integration (2-3 weeks)

**Goals**: Use standard medical terminologies

**Tasks**:
1. ⏳ Integrate terminology server (e.g., Ontoserver, HAPI FHIR)
2. ⏳ Create FHIR ValueSet resources:
   - Radiology modalities (DICOM DCM)
   - Body sites (SNOMED CT)
   - Procedures (LOINC, CPT)
3. ⏳ Update UI to use terminology server for dropdowns
4. ⏳ Migrate existing ModalityType/BodyPart/ScanProtocol data to ValueSets
5. ⏳ (Optional) Deprecate configuration tables in favor of terminology server

**Deliverables**:
- Terminology server integration
- FHIR ValueSet resources
- Updated UI components

---

### Phase 4: Structured Findings (3-4 weeks)

**Goals**: Support structured radiology findings

**Tasks**:
1. ⏳ Create `Observation` resources for key findings:
   - Lesion size measurements
   - Anatomical findings
   - Quantitative measurements
2. ⏳ Link Observations to DiagnosticReport
3. ⏳ Update report creation UI to support structured data entry
4. ⏳ Implement finding templates with Observation patterns

**Example Observation**:
```json
{
  "resourceType": "Observation",
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/observation-category",
      "code": "imaging"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "118565006",
      "display": "Volume of lesion"
    }]
  },
  "subject": {"reference": "Patient/patient-uuid"},
  "effectiveDateTime": "2025-04-16T10:30:00Z",
  "valueQuantity": {
    "value": 2.5,
    "unit": "cm3",
    "system": "http://unitsofmeasure.org",
    "code": "cm3"
  },
  "bodySite": {
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "12738006",
      "display": "Brain structure"
    }]
  }
}
```

**Deliverables**:
- Observation resource support
- Structured finding templates
- Enhanced report UI

---

### Phase 5: Full FHIR Compliance (4-6 weeks)

**Goals**: Complete FHIR R4 compliance

**Tasks**:
1. ⏳ Implement FHIR search parameters:
   - `ImagingStudy?patient=<id>&modality=CT&date=2025-04-16`
   - `DiagnosticReport?patient=<id>&status=final&date=ge2025-01-01`
2. ⏳ Implement FHIR create/update operations
3. ⏳ Add FHIR Bundle support (search results, transactions)
4. ⏳ Implement CapabilityStatement
5. ⏳ Add SMART-on-FHIR authentication
6. ⏳ Enable FHIR bulk data export ($export)
7. ⏳ Pass FHIR Touchstone validation tests

**Deliverables**:
- Full FHIR REST API
- CapabilityStatement resource
- Validation test results

---

## Example FHIR Resources

### Complete Example: CT Brain Study with Report

#### 1. ImagingStudy Resource
```json
{
  "resourceType": "ImagingStudy",
  "id": "ct-brain-20250416",
  "identifier": [{
    "use": "official",
    "system": "urn:dicom:uid",
    "value": "urn:oid:1.2.840.113619.2.55.3.2609.2.1.1"
  }, {
    "use": "secondary",
    "type": {
      "coding": [{
        "system": "http://terminology.hl7.org/CodeSystem/v2-0203",
        "code": "ACSN",
        "display": "Accession ID"
      }]
    },
    "value": "ACC20250416001"
  }],
  "status": "available",
  "modality": [{
    "system": "http://dicom.nema.org/resources/ontology/DCM",
    "code": "CT",
    "display": "Computed Tomography"
  }],
  "subject": {
    "reference": "Patient/patient-12345",
    "display": "John Doe"
  },
  "encounter": {
    "reference": "Encounter/encounter-67890"
  },
  "started": "2025-04-16T10:30:00Z",
  "basedOn": [{
    "reference": "ServiceRequest/radiology-order-001"
  }],
  "referrer": {
    "reference": "Practitioner/dr-johnson",
    "display": "Dr. Sarah Johnson"
  },
  "interpreter": [{
    "reference": "Practitioner/dr-smith",
    "display": "Dr. Michael Smith, MD"
  }],
  "endpoint": [{
    "reference": "Endpoint/dcm4chee-dicomweb"
  }],
  "numberOfSeries": 1,
  "numberOfInstances": 150,
  "procedureCode": [{
    "coding": [{
      "system": "http://loinc.org",
      "code": "24727-0",
      "display": "CT Head W/O Contrast"
    }, {
      "system": "http://www.ama-assn.org/go/cpt",
      "code": "70450",
      "display": "Computed tomography, head or brain; without contrast material"
    }]
  }],
  "location": {
    "reference": "Location/radiology-department",
    "display": "Radiology Department, City Hospital"
  },
  "reasonCode": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "25064002",
      "display": "Headache"
    }],
    "text": "Persistent headache for 2 weeks, rule out intracranial mass"
  }],
  "note": [{
    "text": "Patient unable to lie completely flat due to back pain"
  }],
  "description": "CT Brain without Contrast",
  "series": [{
    "uid": "1.2.840.113619.2.55.3.2609.2.2.1",
    "number": 1,
    "modality": {
      "system": "http://dicom.nema.org/resources/ontology/DCM",
      "code": "CT"
    },
    "description": "Axial Brain",
    "numberOfInstances": 150,
    "endpoint": [{
      "reference": "Endpoint/dcm4chee-dicomweb"
    }],
    "bodySite": {
      "system": "http://snomed.info/sct",
      "code": "12738006",
      "display": "Brain structure"
    },
    "laterality": {
      "system": "http://snomed.info/sct",
      "code": "51440002",
      "display": "Right and left"
    },
    "started": "2025-04-16T10:31:00Z",
    "performer": [{
      "function": {
        "coding": [{
          "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
          "code": "PRF",
          "display": "performer"
        }]
      },
      "actor": {
        "reference": "Practitioner/ct-tech-001",
        "display": "CT Technologist"
      }
    }],
    "instance": [{
      "uid": "1.2.840.113619.2.55.3.2609.2.3.1",
      "sopClass": {
        "system": "urn:ietf:rfc:3986",
        "code": "urn:oid:1.2.840.10008.5.1.4.1.1.2"
      },
      "number": 1
    }]
  }]
}
```

#### 2. DiagnosticReport Resource
```json
{
  "resourceType": "DiagnosticReport",
  "id": "ct-brain-report-001",
  "identifier": [{
    "system": "https://care.ohc.network/fhir/diagnostic-report",
    "value": "REPORT-20250416-001"
  }],
  "basedOn": [{
    "reference": "ServiceRequest/radiology-order-001",
    "display": "CT Brain Order"
  }],
  "status": "final",
  "category": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/v2-0074",
      "code": "RAD",
      "display": "Radiology"
    }, {
      "system": "http://loinc.org",
      "code": "LP29684-5",
      "display": "Radiology"
    }]
  }],
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "24727-0",
      "display": "CT Head W/O Contrast"
    }],
    "text": "CT Brain without Contrast"
  },
  "subject": {
    "reference": "Patient/patient-12345",
    "display": "John Doe"
  },
  "encounter": {
    "reference": "Encounter/encounter-67890"
  },
  "effectiveDateTime": "2025-04-16T10:30:00Z",
  "issued": "2025-04-16T14:30:00Z",
  "performer": [{
    "reference": "Practitioner/dr-smith",
    "display": "Dr. Michael Smith, MD, Radiologist"
  }],
  "resultsInterpreter": [{
    "reference": "Practitioner/dr-smith"
  }],
  "imagingStudy": [{
    "reference": "ImagingStudy/ct-brain-20250416"
  }],
  "media": [{
    "comment": "Representative axial image at level of basal ganglia",
    "link": {
      "reference": "Media/ct-brain-key-image-001"
    }
  }],
  "conclusion": "Normal CT brain. No acute intracranial abnormality. No evidence of mass effect, hemorrhage, or acute infarction.",
  "conclusionCode": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "281900007",
      "display": "No abnormality detected"
    }]
  }],
  "presentedForm": [{
    "contentType": "text/plain",
    "language": "en-US",
    "data": "VEVDSE5JUVVFOgpOb24tY29udHJhc3QgQ1QgYnJhaW4gcGVyZm9ybWVkIHdpdGggNW1tIGF4aWFsIHNsaWNlcyBmcm9tIHRoZSBza3VsbCBiYXNlIHRvIHRoZSB2ZXJ0ZXguCgpGSU5ESU5HUzoKVGhlIGJyYWluIHBhcmVuY2h5bWEgZGVtb25zdHJhdGVzIG5vcm1hbCBhdHRlbnVhdGlvbi4gVGhlIGdyYXkgd2hpdGUgbWF0dGVyIGRpZmZlcmVudGlhdGlvbiBpcyBwcmVzZXJ2ZWQuIE5vIGFjdXRlIGludHJhY3JhbmlhbCBoZW1vcnJoYWdlLiBObyBldmlkZW5jZSBvZiBhY3V0ZSBpbmZhcmN0aW9uLiBObyBtYXNzIGVmZmVjdC4gVGhlIHZlbnRyaWNsZXMgYW5kIHN1bGNpIGFyZSBub3JtYWwgaW4gc2l6ZSBhbmQgY29uZmlndXJhdGlvbi4gVGhlIG1pZGxpbmUgc3RydWN0dXJlcyBhcmUgaW50YWN0LgoKSU1QUkVTU0lPTjoKTm9ybWFsIENUIGJyYWluLiBObyBhY3V0ZSBpbnRyYWNyYW5pYWwgYWJub3JtYWxpdHku",
    "title": "Radiology Report - CT Brain",
    "creation": "2025-04-16T14:30:00Z"
  }]
}
```

#### 3. ServiceRequest Resource
```json
{
  "resourceType": "ServiceRequest",
  "id": "radiology-order-001",
  "identifier": [{
    "system": "https://care.ohc.network/fhir/service-request",
    "value": "ORDER-20250415-001"
  }],
  "status": "completed",
  "intent": "order",
  "category": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "363679005",
      "display": "Imaging"
    }]
  }],
  "priority": "routine",
  "code": {
    "coding": [{
      "system": "http://loinc.org",
      "code": "24727-0",
      "display": "CT Head W/O Contrast"
    }],
    "text": "CT Brain without Contrast"
  },
  "orderDetail": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "77477000",
      "display": "Computerized axial tomography"
    }],
    "text": "Axial CT without contrast"
  }],
  "subject": {
    "reference": "Patient/patient-12345"
  },
  "encounter": {
    "reference": "Encounter/encounter-67890"
  },
  "occurrenceDateTime": "2025-04-16T10:00:00Z",
  "authoredOn": "2025-04-15T14:00:00Z",
  "requester": {
    "reference": "Practitioner/dr-johnson",
    "display": "Dr. Sarah Johnson, Internal Medicine"
  },
  "performer": [{
    "reference": "Practitioner/dr-smith"
  }],
  "locationReference": [{
    "reference": "Location/radiology-department"
  }],
  "reasonCode": [{
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "25064002",
      "display": "Headache"
    }],
    "text": "Persistent headache for 2 weeks, rule out intracranial mass"
  }],
  "supportingInfo": [{
    "reference": "ImagingStudy/ct-brain-20250416",
    "display": "Completed CT Brain study"
  }],
  "note": [{
    "text": "Patient reports headache worse in the morning. No neurological deficits on exam."
  }]
}
```

#### 4. Endpoint Resource (DCM4CHEE)
```json
{
  "resourceType": "Endpoint",
  "id": "dcm4chee-dicomweb",
  "status": "active",
  "connectionType": {
    "system": "http://terminology.hl7.org/CodeSystem/endpoint-connection-type",
    "code": "dicom-wado-rs",
    "display": "DICOM WADO-RS"
  },
  "name": "DCM4CHEE DICOMweb Endpoint",
  "managingOrganization": {
    "reference": "Organization/city-hospital",
    "display": "City Hospital"
  },
  "contact": [{
    "system": "email",
    "value": "radiology-it@cityhospital.org"
  }],
  "period": {
    "start": "2025-01-01"
  },
  "payloadType": [{
    "coding": [{
      "system": "http://terminology.hl7.org/CodeSystem/endpoint-payload-type",
      "code": "DICOM",
      "display": "DICOM"
    }]
  }],
  "payloadMimeType": [
    "application/dicom",
    "application/dicom+json",
    "application/dicom+xml"
  ],
  "address": "http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs",
  "header": [
    "Accept: application/dicom+json"
  ]
}
```

---

## Recommendations

### Immediate Actions (Now - 1 month)

1. **✅ Adopt FHIR Resource Mappings**
   - Use this document as design guide
   - Review with development team
   - Prioritize Phase 1 tasks

2. **⏳ Enhance Data Models**
   - Add missing fields (encounter, status, codes)
   - Create database migrations
   - Update API serializers

3. **⏳ Implement FHIR API (Read-Only)**
   - Install FHIR library (django-fhir)
   - Create GET endpoints for ImagingStudy, DiagnosticReport
   - Test with FHIR clients (Postman, Touchstone)

4. **⏳ Document FHIR Capabilities**
   - Create CapabilityStatement resource
   - Document supported resources and operations
   - Publish to API documentation

### Short-Term (1-3 months)

5. **⏳ Integrate Terminology Server**
   - Deploy Ontoserver or HAPI FHIR terminology module
   - Create ValueSet resources for modalities, body sites, procedures
   - Update UI to use terminology server

6. **⏳ Implement Report Status Workflow**
   - Add status field: draft → preliminary → final → amended
   - Track state transitions in audit trail
   - Add API support for status updates

7. **⏳ Add Encounter Context**
   - Link reports to encounters
   - Enable encounter-based queries
   - Support inpatient vs outpatient workflows

8. **⏳ FHIR Testing & Validation**
   - Test with FHIR Touchstone validator
   - Fix validation errors
   - Document conformance

### Long-Term (3-6 months)

9. **⏳ Structured Findings (Observations)**
   - Define Observation profiles for common findings
   - Update UI for structured data entry
   - Link Observations to DiagnosticReport

10. **⏳ Full FHIR CRUD Operations**
    - Implement POST (create), PUT (update), DELETE
    - Add FHIR search parameters
    - Support FHIR Bundles for transactions

11. **⏳ SMART-on-FHIR Authentication**
    - Implement OAuth 2.0 / OpenID Connect
    - Support SMART App Launch
    - Enable third-party app integration

12. **⏳ FHIR Subscriptions**
    - Notify external systems of new reports
    - Support real-time integration
    - Replace webhook with FHIR Subscription

### Strategic Considerations

13. **📊 Interoperability Benefits**
    - Enable integration with EHR systems (Epic, Cerner)
    - Support healthcare data exchange (HIE)
    - Facilitate clinical research data sharing
    - Improve care coordination

14. **📊 Standards Compliance**
    - Align with US Core profiles
    - Support IHE radiology profiles (XDS-I.b)
    - Prepare for 21st Century Cures Act requirements
    - Enable Certified EHR Technology (CEHRT) integration

15. **📊 Business Value**
    - Attract healthcare customers requiring FHIR
    - Reduce custom integration costs
    - Enable app ecosystem (SMART apps)
    - Future-proof architecture

---

## Conclusion

The care_radiology plugin has a solid foundation for FHIR compliance with direct mappings to core resources:
- ✅ DicomStudy → ImagingStudy
- ✅ StudyReport → DiagnosticReport
- ✅ RadiologyServiceRequest → ServiceRequest

**Key recommendations**:
1. Enhance data models with missing FHIR fields
2. Implement FHIR REST API (start read-only)
3. Integrate terminology server for standard codes
4. Add structured findings via Observation resources
5. Support full FHIR R4 specification over time

By following the phased roadmap, care_radiology can achieve full FHIR compliance and enable seamless healthcare interoperability.

---

**Document Metadata**:
- Version: 1.0
- Date: 2026-04-22
- Author: Care Development Team
- FHIR Version: R4 (primary), R5 (notes)
- Status: Draft for Review

**References**:
- [FHIR R4 Specification](http://hl7.org/fhir/R4/)
- [ImagingStudy Resource](http://hl7.org/fhir/R4/imagingstudy.html)
- [DiagnosticReport Resource](http://hl7.org/fhir/R4/diagnosticreport.html)
- [IHE Radiology Profiles](https://wiki.ihe.net/index.php/Radiology)
- [DICOM to FHIR Mapping](http://dicom.nema.org/medical/dicom/current/output/html/part18.html)
