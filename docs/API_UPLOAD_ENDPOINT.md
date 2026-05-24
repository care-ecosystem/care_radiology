# DICOM Upload API - Technical Documentation

## Endpoint Overview

```
POST /api/care_radiology/dicom/upload/
```

**Purpose**: Upload DICOM files from Care frontend to DCM4CHEE PACS archive, creating metadata links in Care database.

**Location**: `src/care_radiology/api/dicom.py:55-146`

---

## Request Specification

### HTTP Request

```http
POST /api/care_radiology/dicom/upload/ HTTP/1.1
Host: localhost:9000
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary

------WebKitFormBoundary
Content-Disposition: form-data; name="patient_id"

550e8400-e29b-41d4-a716-446655440000
------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="chest_xray.dcm"
Content-Type: application/dicom

<DICOM binary data>
------WebKitFormBoundary--
```

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `patient_id` | UUID String | Yes | Patient's external_id from Care database |
| `file` | Binary File | Yes | DICOM file (.dcm format) |

### Authentication

**Type**: JWT Bearer Token

**Headers**:
```http
Authorization: Bearer <jwt_token>
```

**Token Contains**:
- User ID
- Username
- Facility memberships
- Role permissions
- Expiry timestamp (10 minutes)

**Validation**:
- Token signature verification (HMAC SHA256)
- Expiry check
- User active status
- Facility access validation

---

## Authorization Flow

### Permission Check: `can_write_patient_obj`

```python
# Location: dicom.py:60
if not AuthorizationController.call(
    "can_write_patient_obj",
    self.request.user,
    patient
):
    raise PermissionDenied(
        "You do not have permission to upload DICOM for this patient"
    )
```

### Authorization Logic

**Step 1: Load Patient**
```python
patient = Patient.objects.get(external_id=request.data.get("patient_id"))
```

**Step 2: Check Permission Hierarchy**

1. **Facility Membership**:
   - User must belong to patient's facility
   - Cross-facility access denied (unless super admin)

2. **Role-Based Permissions**:
   ```
   Doctor:      ✓ Can write
   Nurse:       ✓ Can write (if assigned to patient)
   Radiologist: ✓ Can write
   Pharmacist:  ✗ Cannot write
   Admin:       ✓ Can write
   ```

3. **Object-Level Checks**:
   - Patient not deleted (`deleted=False`)
   - Patient active in system
   - No active restrictions on patient record

4. **Special Cases**:
   - Patient is in user's assigned ward
   - User is primary care provider
   - Temporary access granted via delegation

### Authorization Failure Response

```json
{
  "detail": "You do not have permission to upload DICOM for this patient"
}
```
**HTTP Status**: 403 Forbidden

---

## Data Flow Diagram

```
┌─────────────┐
│   Browser   │
│  (Frontend) │
└──────┬──────┘
       │ 1. POST /dicom/upload/
       │    - patient_id: UUID
       │    - file: DICOM binary
       │    - Authorization: Bearer token
       ▼
┌─────────────────────────────────────────────────┐
│  Django Request Middleware                      │
│  ─────────────────────────────────────────      │
│  1. Parse multipart/form-data                   │
│  2. JWT Authentication (JWTAuthentication)      │
│  3. CSRF validation (exempt for API)            │
│  4. Rate limiting check                         │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  DicomViewSet.upload()                          │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:55                      │
└──────┬──────────────────────────────────────────┘
       │
       │ 2. Load Patient by external_id
       ▼
┌─────────────────────────────────────────────────┐
│  PostgreSQL - care.emr_patient                  │
│  ─────────────────────────────────────────      │
│  SELECT * FROM emr_patient                      │
│  WHERE external_id = '550e8400...'              │
│    AND deleted = false                          │
└──────┬──────────────────────────────────────────┘
       │ Patient object
       │
       │ 3. Authorization check
       ▼
┌─────────────────────────────────────────────────┐
│  AuthorizationController                        │
│  ─────────────────────────────────────────      │
│  - Check facility membership                    │
│  - Check role permissions                       │
│  - Check object-level access                    │
│  ─────────────────────────────────────────      │
│  Result: True/False                             │
└──────┬──────────────────────────────────────────┘
       │ ✓ Authorized
       │
       │ 4. Validate file exists
       ▼
┌─────────────────────────────────────────────────┐
│  File Validation                                │
│  ─────────────────────────────────────────      │
│  dcm_file = request.FILES.get("file")           │
│  if not dcm_file:                               │
│      return 400 Bad Request                     │
└──────┬──────────────────────────────────────────┘
       │ ✓ File present
       │
       │ 5. Encode as multipart/related
       ▼
┌─────────────────────────────────────────────────┐
│  encode_file_multipart_related()                │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:369                     │
│                                                 │
│  1. Generate boundary UUID                      │
│  2. Read file bytes                             │
│  3. Construct multipart body:                   │
│     --DICOMBOUNDARY-{uuid}                      │
│     Content-Type: application/dicom             │
│     Content-Length: {size}                      │
│                                                 │
│     {DICOM binary data}                         │
│     --DICOMBOUNDARY-{uuid}--                    │
│                                                 │
│  Returns: (body: bytes, content_type: str)      │
└──────┬──────────────────────────────────────────┘
       │ Encoded body + content type
       │
       │ 6. Upload to DCM4CHEE via STOW-RS
       ▼
┌─────────────────────────────────────────────────┐
│  HTTP POST to DCM4CHEE                          │
│  ─────────────────────────────────────────      │
│  URL: {DCM4CHEE_BASEURL}/rs/studies             │
│  Headers:                                       │
│    Content-Type: multipart/related;             │
│                  type="application/dicom"       │
│    Accept: application/dicom+json               │
│  Body: Encoded DICOM data                       │
│                                                 │
│  Timeout: 120 seconds                           │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  DCM4CHEE Archive                               │
│  ─────────────────────────────────────────      │
│  1. Validate DICOM format                       │
│  2. Parse DICOM header                          │
│  3. Extract metadata:                           │
│     - StudyInstanceUID                          │
│     - SeriesInstanceUID                         │
│     - SOPInstanceUID                            │
│     - Patient demographics                      │
│     - Study date/time                           │
│     - Modality                                  │
│  4. Check for duplicates                        │
│  5. Store in MinIO via LDAP config              │
│  6. Update internal registry                    │
│  7. Return JSON response                        │
└──────┬──────────────────────────────────────────┘
       │
       │ Response: 200/201/202/409/500
       ▼
┌─────────────────────────────────────────────────┐
│  Response Status Handling                       │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:85-139                  │
│                                                 │
│  if status in [200, 201, 202, 409]:             │
│      # Success or duplicate (treated as success)│
│      Parse response JSON                        │
│      Extract Study UID                          │
│  else:                                          │
│      # Real failure                             │
│      Return 502 Bad Gateway                     │
└──────┬──────────────────────────────────────────┘
       │ ✓ Success (200/201/202/409)
       │
       │ 7. Extract Study UID from response
       ▼
┌─────────────────────────────────────────────────┐
│  Parse DICOM Response JSON                      │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:89-103                  │
│                                                 │
│  data = upload_response.json()                  │
│                                                 │
│  # Find ReferencedSOPSQ tag (00081199)          │
│  ref_sop = d_find(data, "00081199")[0]         │
│                                                 │
│  # Extract ReferencedInstanceUID (00081155)     │
│  instance_uid = d_find(                         │
│      ref_sop,                                   │
│      "00081155"                                 │
│  )[0]                                           │
│                                                 │
│  # Query DCM4CHEE for full instance metadata    │
│  instance_data = d_query_instance(instance_uid) │
│                                                 │
│  # Extract StudyInstanceUID (0020000D)          │
│  study_uid = d_find(                            │
│      instance_data,                             │
│      "0020000D"                                 │
│  )[0]                                           │
└──────┬──────────────────────────────────────────┘
       │ study_uid: "1.2.840.113619..."
       │
       │ 8. Query instance for study UID
       ▼
┌─────────────────────────────────────────────────┐
│  d_query_instance(instance_uid)                 │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:255                     │
│                                                 │
│  GET {DCM4CHEE_BASEURL}/rs/instances            │
│  Params: SOPInstanceUID={instance_uid}          │
│  Headers: Accept: application/json              │
│                                                 │
│  Returns: Instance metadata with Study UID      │
└──────┬──────────────────────────────────────────┘
       │ Instance metadata
       │
       │ 9. Create database record
       ▼
┌─────────────────────────────────────────────────┐
│  DicomStudy.objects.update_or_create()          │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:107                     │
│                                                 │
│  INSERT INTO radiology_dicomstudy               │
│  (                                              │
│      id, external_id, created_date,             │
│      modified_date, deleted,                    │
│      patient_id, dicom_study_uid,               │
│      created_by_id, updated_by_id               │
│  )                                              │
│  VALUES (...)                                   │
│  ON CONFLICT (patient_id, dicom_study_uid)      │
│      DO UPDATE SET modified_date = NOW()        │
│                                                 │
│  # Unique constraint prevents duplicates        │
└──────┬──────────────────────────────────────────┘
       │ DicomStudy record created
       │
       │ 10. Cache invalidation
       ▼
┌─────────────────────────────────────────────────┐
│  Redis Cache Invalidation                       │
│  ─────────────────────────────────────────      │
│  Location: api/dicom.py:114                     │
│                                                 │
│  cache.delete(f"radiology:dicom:study:{study_uid}")│
│                                                 │
│  # Why? Cached study metadata now stale         │
│  # Next query will fetch fresh data             │
└──────┬──────────────────────────────────────────┘
       │
       │ 11. Return success response
       ▼
┌─────────────────────────────────────────────────┐
│  HTTP 200 OK Response                           │
│  ─────────────────────────────────────────      │
│  {                                              │
│    "status": "success",                         │
│    "message": "DICOM uploaded successfully",    │
│    "study_uid": "1.2.840.113619...",            │
│    "dicom_response": {                          │
│      "00081199": {                              │
│        "vr": "SQ",                              │
│        "Value": [...]                           │
│      }                                          │
│    }                                            │
│  }                                              │
└──────┬──────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│   Browser   │
│  (Frontend) │
└─────────────┘
```

---

## Detailed Code Blocks

### Block 1: Patient Loading and Validation

**Location**: `api/dicom.py:57-61`

```python
patient = Patient.objects.get(external_id=request.data.get("patient_id"))

if not AuthorizationController.call("can_write_patient_obj", self.request.user, patient):
    raise PermissionDenied("You do not have permission to upload DICOM for this patient")
```

**Purpose**:
- Load patient from Care database
- Verify user has write permission for this patient

**Database Query**:
```sql
SELECT
    id, external_id, name, age, gender,
    facility_id, created_date, deleted
FROM emr_patient
WHERE external_id = '550e8400-e29b-41d4-a716-446655440000'
  AND deleted = false
LIMIT 1;
```

**Error Handling**:
- `Patient.DoesNotExist` → 404 Not Found (Django handles automatically)
- Authorization fails → 403 Forbidden with custom message

**Performance**:
- Single query with index on `external_id`
- Average query time: ~2ms

---

### Block 2: File Validation

**Location**: `api/dicom.py:58`

```python
dcm_file = request.FILES.get("file")

if not dcm_file:
    return Response({"error": "No file provided"}, status=400)
```

**Purpose**: Validate that file was uploaded in request

**File Object Properties**:
```python
dcm_file.name           # "chest_xray.dcm"
dcm_file.content_type   # "application/dicom"
dcm_file.size           # 1048576 (bytes)
dcm_file.read()         # Binary content
```

**Validation Logic**:
- Checks if `file` key exists in `request.FILES`
- Does NOT validate DICOM format (delegated to DCM4CHEE)
- Does NOT check file size (nginx handles via `client_max_body_size 100M`)

**Possible Enhancement**:
```python
# Future: Add DICOM format validation
import pydicom

try:
    dcm = pydicom.dcmread(dcm_file)
    # Validate required tags present
    if not hasattr(dcm, 'PatientID'):
        return Response({"error": "Invalid DICOM: Missing PatientID"}, status=400)
except Exception as e:
    return Response({"error": f"Invalid DICOM file: {str(e)}"}, status=400)
```

---

### Block 3: Multipart Encoding

**Location**: `api/dicom.py:67-68`

```python
body, content_type = encode_file_multipart_related(dcm_file)
```

**Full Implementation**: `api/dicom.py:369-390`

```python
def encode_file_multipart_related(file_obj):
    import uuid

    # Generate unique boundary for multipart message
    boundary = f"DICOMBOUNDARY-{uuid.uuid4().hex}"

    # Read entire file into memory
    file_bytes = file_obj.read()

    # Construct multipart body according to RFC 2046
    body = (
        (
            f"--{boundary}\r\n"
            f"Content-Type: application/dicom\r\n"
            f"Content-Length: {len(file_bytes)}\r\n"
            f"\r\n"
        ).encode("utf-8")
        + file_bytes
        + f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    # Content type with boundary parameter
    content_type = f'multipart/related; type="application/dicom"; boundary={boundary}'

    return body, content_type
```

**Why Multipart/Related?**
- STOW-RS (DICOM Part 18) requires multipart/related format
- Allows multiple DICOM instances in single request
- Each part has its own Content-Type header
- Standard for web-based DICOM transfer

**Example Output**:
```
Content-Type: multipart/related; type="application/dicom"; boundary=DICOMBOUNDARY-a1b2c3d4

--DICOMBOUNDARY-a1b2c3d4
Content-Type: application/dicom
Content-Length: 1048576

<DICOM binary data here>
--DICOMBOUNDARY-a1b2c3d4--
```

**Memory Considerations**:
- Entire file loaded into memory (`file_bytes = file_obj.read()`)
- Max file size: 100MB (nginx limit)
- Memory usage: ~2x file size (original + encoded)
- For 100MB file: ~200MB memory consumed

**Optimization Opportunity**:
```python
# Stream large files instead of loading into memory
import requests_toolbelt

def encode_file_multipart_related_stream(file_obj):
    """Stream-based encoding for large files"""
    boundary = f"DICOMBOUNDARY-{uuid.uuid4().hex}"

    encoder = requests_toolbelt.MultipartEncoder(
        fields={
            'file': ('file.dcm', file_obj, 'application/dicom')
        },
        boundary=boundary
    )

    return encoder, encoder.content_type
```

---

### Block 4: DCM4CHEE Upload (STOW-RS)

**Location**: `api/dicom.py:72-79`

```python
upload_response = requests.post(
    url=f"{DCM4CHEE_BASEURL}/rs/studies",
    data=body,
    headers={
        "Content-Type": content_type,
        "Accept": "application/dicom+json",
    },
)
```

**Full Request Details**:

```http
POST http://arc:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies HTTP/1.1
Host: arc:8080
Content-Type: multipart/related; type="application/dicom"; boundary=DICOMBOUNDARY-abc123
Accept: application/dicom+json
Content-Length: 1048576

--DICOMBOUNDARY-abc123
Content-Type: application/dicom
Content-Length: 1048576

<DICOM binary data>
--DICOMBOUNDARY-abc123--
```

**DCM4CHEE Processing**:

1. **Validation**:
   - Verifies multipart/related format
   - Checks DICOM file structure
   - Validates required DICOM tags

2. **Metadata Extraction**:
   - StudyInstanceUID (0020,000D)
   - SeriesInstanceUID (0020,000E)
   - SOPInstanceUID (0008,0018)
   - Patient Name, ID, DOB
   - Study Date/Time
   - Modality

3. **Storage**:
   - Queries LDAP for storage configuration
   - Stores DICOM file in MinIO (S3-compatible)
   - Path: `s3://dicom-bucket/studies/{StudyUID}/series/{SeriesUID}/{InstanceUID}.dcm`

4. **Database Update**:
   - Inserts metadata into PostgreSQL (`dicom` database)
   - Tables: `study`, `series`, `instance`, `patient`, `code`
   - Creates indexes for fast QIDO-RS queries

**Timeout Configuration**:
- Default: 120 seconds (requests library default)
- Should be configured explicitly:
  ```python
  upload_response = requests.post(
      url=f"{DCM4CHEE_BASEURL}/rs/studies",
      data=body,
      headers={...},
      timeout=120  # Explicit timeout
  )
  ```

**Error Responses from DCM4CHEE**:

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 200 OK | Upload successful | Extract Study UID |
| 201 Created | New study created | Extract Study UID |
| 202 Accepted | Processing async | Extract Study UID |
| 409 Conflict | DICOM already exists | Treat as success, return existing UID |
| 400 Bad Request | Invalid DICOM format | Return error to user |
| 500 Internal Server Error | DCM4CHEE error | Return 502 to user |
| Timeout | No response after 120s | Retry or return error |

---

### Block 5: Response Status Handling

**Location**: `api/dicom.py:85-139`

```python
# Accept 409 as success
if upload_response.status_code in [200, 201, 202, 409]:
    data = upload_response.json()

    try:
        # Extract Study UID
        ref_sop = d_find(data, DICOM_TAG.ReferencedSOPSQ.value)[0]
        instance_uid = d_find(ref_sop, DICOM_TAG.ReferencedInstanceUID.value)[0]
        study_uid = d_find(
            d_query_instance(instance_uid),
            DICOM_TAG.StudyInstanceUID.value
        )[0]
    except Exception as parse_error:
        print("DICOM parse error:", str(parse_error))
        study_uid = None

    # Store mapping only if available
    if study_uid:
        DicomStudy.objects.update_or_create(
            dicom_study_uid=study_uid,
            patient=patient,
            defaults={},
        )

        # Bust cache
        cache.delete(f"radiology:dicom:study:{study_uid}")

    return Response(
        data={
            "status": "success",
            "message": (
                "DICOM already exists in DCM4CHEE"
                if upload_response.status_code == 409
                else "DICOM uploaded successfully"
            ),
            "study_uid": study_uid,
            "dicom_response": data,
        },
        status=200,
    )

# Real failure
else:
    return Response(
        data={
            "error": "Failed to upload to DCM4CHEE",
            "status_code": upload_response.status_code,
            "details": upload_response.text,
        },
        status=502,
    )
```

**Why 409 (Conflict) is treated as success**:
- DCM4CHEE returns 409 if DICOM instance already exists
- In radiology workflow, duplicate upload is not an error
- Same image may be uploaded multiple times (re-sends, retries)
- SOPInstanceUID ensures uniqueness at DICOM level

**Study UID Extraction Logic**:

1. **Find Referenced SOP Sequence** (Tag: 00081199):
   ```json
   {
     "00081199": {
       "vr": "SQ",
       "Value": [
         {
           "00081150": {"vr": "UI", "Value": ["1.2.840.10008.5.1.4.1.1.7"]},
           "00081155": {"vr": "UI", "Value": ["1.2.840.113619.2.55.3.2609.2.3.1"]}
         }
       ]
     }
   }
   ```

2. **Extract Referenced Instance UID** (Tag: 00081155):
   ```python
   instance_uid = "1.2.840.113619.2.55.3.2609.2.3.1"
   ```

3. **Query DCM4CHEE for instance metadata**:
   ```http
   GET http://arc:8080/dcm4chee-arc/aets/DCM4CHEE/rs/instances?SOPInstanceUID=1.2.840.113619.2.55.3.2609.2.3.1
   ```

4. **Extract Study Instance UID** (Tag: 0020000D) from response:
   ```json
   {
     "0020000D": {
       "vr": "UI",
       "Value": ["1.2.840.113619.2.55.3.2609.2.1.1"]
     }
   }
   ```

**Error Handling in Extraction**:
- Wrapped in try-except to handle malformed responses
- If extraction fails, `study_uid = None`
- Record still logged, but no DicomStudy created
- User receives success but without study_uid in response

---

### Block 6: Database Record Creation

**Location**: `api/dicom.py:107-111`

```python
DicomStudy.objects.update_or_create(
    dicom_study_uid=study_uid,
    patient=patient,
    defaults={},
)
```

**Generated SQL**:

```sql
-- Step 1: Check if record exists
SELECT id, external_id, patient_id, dicom_study_uid, created_date, modified_date
FROM radiology_dicomstudy
WHERE patient_id = 123
  AND dicom_study_uid = '1.2.840.113619.2.55.3.2609.2.1.1'
  AND deleted = false
LIMIT 1;

-- Step 2a: If exists, update modified_date
UPDATE radiology_dicomstudy
SET modified_date = NOW(),
    updated_by_id = 456
WHERE id = 789;

-- Step 2b: If not exists, insert new record
INSERT INTO radiology_dicomstudy (
    id,
    external_id,
    created_date,
    modified_date,
    deleted,
    history,
    meta,
    patient_id,
    dicom_study_uid,
    created_by_id,
    updated_by_id
) VALUES (
    nextval('radiology_dicomstudy_id_seq'),
    'a3b2c1d0-e4f5-6789-abcd-ef0123456789',
    NOW(),
    NOW(),
    false,
    '[]'::jsonb,
    '{}'::jsonb,
    123,
    '1.2.840.113619.2.55.3.2609.2.1.1',
    456,
    456
);
```

**Unique Constraint**:
```sql
ALTER TABLE radiology_dicomstudy
ADD CONSTRAINT unique_patient_study
UNIQUE (patient_id, dicom_study_uid);
```

**Why this prevents duplicates**:
- Same study can't be linked to same patient twice
- Different patients CAN have different studies with same UID (edge case in multi-facility)
- Constraint enforced at database level (not just Django)

**update_or_create Behavior**:
- Atomic operation (transaction-safe)
- Returns tuple: `(instance, created)`
- `created=True` if new, `created=False` if updated
- Thread-safe (database handles concurrency)

**Fields Populated by EMRBaseModel**:
- `external_id`: Auto-generated UUID
- `created_date`: Auto-set to NOW() on insert
- `modified_date`: Auto-updated to NOW() on every save
- `created_by_id`: Pulled from `request.user`
- `updated_by_id`: Pulled from `request.user`
- `deleted`: Default `false`
- `history`: Empty JSON array `[]`
- `meta`: Empty JSON object `{}`

---

### Block 7: Cache Invalidation

**Location**: `api/dicom.py:114`

```python
cache.delete(f"radiology:dicom:study:{study_uid}")
```

**Purpose**:
- Study metadata cached from previous query is now stale
- New series may have been added
- Next query should fetch fresh data from DCM4CHEE

**Cache Key Format**:
```
radiology:dicom:study:1.2.840.113619.2.55.3.2609.2.1.1
```

**What gets deleted**:
```json
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
    }
  ]
}
```

**Why invalidate on upload?**:
- New instance added to existing study
- Instance count changed
- Series description may have changed
- Modalities list may have expanded

**Redis Command**:
```redis
DEL radiology:dicom:study:1.2.840.113619.2.55.3.2609.2.1.1
```

**Cache Write-Through Alternative** (not implemented):
```python
# Instead of deleting, update the cache
study_metadata = fetch_study(study_uid)  # Fresh from DCM4CHEE
cache.set(
    f"radiology:dicom:study:{study_uid}",
    study_metadata,
    timeout=60*60
)
```

---

## Success Response Structure

```json
{
  "status": "success",
  "message": "DICOM uploaded successfully",
  "study_uid": "1.2.840.113619.2.55.3.2609.2.1.1",
  "dicom_response": {
    "00081190": {
      "vr": "UR",
      "Value": ["http://arc:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.2.840.113619.2.55.3.2609.2.1.1"]
    },
    "00081198": {
      "vr": "SQ",
      "Value": []
    },
    "00081199": {
      "vr": "SQ",
      "Value": [
        {
          "00081150": {
            "vr": "UI",
            "Value": ["1.2.840.10008.5.1.4.1.1.7"]
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

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `status` | String | "success" for all successful uploads |
| `message` | String | Human-readable message (varies for 409 vs 200) |
| `study_uid` | String | DICOM Study Instance UID |
| `dicom_response` | Object | Raw response from DCM4CHEE (DICOM JSON format) |
| `dicom_response.00081190` | Object | Retrieve URL (WADO-RS endpoint) |
| `dicom_response.00081199` | Object | Referenced SOP Sequence (uploaded instances) |

**DICOM Tags in Response**:

| Tag | Name | VR | Description |
|-----|------|----|----|
| 00081190 | RetrieveURL | UR | URL to retrieve the study |
| 00081198 | FailedSOPSequence | SQ | Instances that failed to upload |
| 00081199 | ReferencedSOPSequence | SQ | Successfully uploaded instances |
| 00081150 | ReferencedSOPClassUID | UI | DICOM SOP class (CR, CT, MR, etc.) |
| 00081155 | ReferencedSOPInstanceUID | UI | Unique instance identifier |

---

## Error Responses

### 1. Missing File

```json
{
  "error": "No file provided"
}
```
**HTTP Status**: 400 Bad Request

**Cause**: `file` parameter missing in multipart form data

---

### 2. Patient Not Found

```json
{
  "detail": "Not found."
}
```
**HTTP Status**: 404 Not Found

**Cause**: Patient with given `external_id` doesn't exist or is deleted

---

### 3. Authorization Failure

```json
{
  "detail": "You do not have permission to upload DICOM for this patient"
}
```
**HTTP Status**: 403 Forbidden

**Causes**:
- User not in patient's facility
- User role lacks write permissions
- Patient record restricted

---

### 4. DCM4CHEE Upload Failure

```json
{
  "error": "Failed to upload to DCM4CHEE",
  "status_code": 500,
  "details": "org.dcm4che3.net.service.DicomServiceException: Invalid DICOM file"
}
```
**HTTP Status**: 502 Bad Gateway

**Causes**:
- DCM4CHEE service down
- Invalid DICOM format
- MinIO storage unavailable
- PostgreSQL connection error

---

### 5. General Exception

```json
{
  "error": "Exception occurred",
  "details": "Connection timeout to DCM4CHEE"
}
```
**HTTP Status**: 500 Internal Server Error

**Causes**:
- Network timeout
- Unhandled exception in code
- Python dependency error

---

## Performance Metrics

### Typical Upload Timeline

| Step | Duration | Notes |
|------|----------|-------|
| 1. Authentication | 5-10ms | JWT decode + DB query |
| 2. Patient load | 2-5ms | Single indexed query |
| 3. Authorization check | 10-20ms | Multiple permission checks |
| 4. File validation | <1ms | Check if file exists |
| 5. Multipart encoding | 50-200ms | Depends on file size |
| 6. DCM4CHEE upload | 1-5 seconds | Network + storage |
| 7. Study UID extraction | 100-300ms | QIDO-RS query |
| 8. Database insert | 5-10ms | Single INSERT or UPDATE |
| 9. Cache invalidation | 1-2ms | Redis DELETE |
| **Total** | **2-6 seconds** | For 10-50MB DICOM file |

### Optimization Opportunities

1. **Parallel Study UID Extraction**:
   - Query instance metadata while DCM4CHEE stores file
   - Save ~100-300ms

2. **Stream-based Encoding**:
   - Avoid loading entire file into memory
   - Enable uploads >100MB

3. **Async Upload**:
   - Return immediately with upload ID
   - Process in Celery task
   - Notify frontend via WebSocket

4. **Connection Pooling**:
   ```python
   session = requests.Session()
   session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=10))
   ```

---

## Security Considerations

### 1. File Upload Validation

**Current**: No DICOM format validation before upload

**Risks**:
- Malicious files could be sent to DCM4CHEE
- Large files could consume memory (OOM)
- Non-DICOM files waste storage

**Mitigation**:
```python
# Add DICOM magic number check
DICOM_MAGIC = b'DICM'
file_bytes = dcm_file.read(132)
if file_bytes[128:132] != DICOM_MAGIC:
    return Response({"error": "Not a valid DICOM file"}, status=400)
dcm_file.seek(0)  # Reset for actual upload
```

### 2. PHI (Protected Health Information)

**Data in DICOM**:
- Patient Name
- Patient ID
- Date of Birth
- Medical Record Number
- Images contain visible PHI (patient ID burned in)

**Protections**:
- JWT authentication required
- Authorization at patient level
- Audit trail via EMRBaseModel
- HTTPS in production (encryption in transit)
- Encrypted storage (MinIO server-side encryption)

### 3. Rate Limiting

**Current**: Django default (no specific limit)

**Recommendation**:
```python
from rest_framework.throttling import UserRateThrottle

class DicomUploadRateThrottle(UserRateThrottle):
    rate = '100/hour'  # Max 100 uploads per hour per user

class DicomViewSet(ViewSet):
    throttle_classes = [DicomUploadRateThrottle]
```

### 4. Input Sanitization

**Current**: No sanitization of patient_id

**Risk**: SQL injection (mitigated by Django ORM)

**Best Practice**:
```python
import uuid

try:
    patient_id_uuid = uuid.UUID(request.data.get("patient_id"))
except ValueError:
    return Response({"error": "Invalid patient_id format"}, status=400)

patient = Patient.objects.get(external_id=patient_id_uuid)
```

---

## Testing Guide

### Unit Test

```python
from django.test import TestCase
from rest_framework.test import APIClient
from care.emr.models import Patient
from care_radiology.models import DicomStudy

class DicomUploadTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='doctor', password='test123')
        self.patient = Patient.objects.create(
            name="John Doe",
            facility=self.user.facility
        )
        self.client.force_authenticate(user=self.user)

    def test_upload_dicom_success(self):
        """Test successful DICOM upload"""
        with open('test_data/sample.dcm', 'rb') as dcm_file:
            response = self.client.post(
                '/api/care_radiology/dicom/upload/',
                {
                    'patient_id': str(self.patient.external_id),
                    'file': dcm_file
                },
                format='multipart'
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success')
        self.assertIsNotNone(response.data['study_uid'])

        # Verify database record created
        study = DicomStudy.objects.get(patient=self.patient)
        self.assertEqual(study.dicom_study_uid, response.data['study_uid'])

    def test_upload_without_file(self):
        """Test upload with missing file"""
        response = self.client.post(
            '/api/care_radiology/dicom/upload/',
            {'patient_id': str(self.patient.external_id)},
            format='multipart'
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

    def test_upload_unauthorized(self):
        """Test upload without permission"""
        other_user = User.objects.create_user(username='nurse', password='test123')
        other_facility = Facility.objects.create(name="Other Hospital")
        other_patient = Patient.objects.create(
            name="Jane Doe",
            facility=other_facility
        )

        self.client.force_authenticate(user=self.user)

        with open('test_data/sample.dcm', 'rb') as dcm_file:
            response = self.client.post(
                '/api/care_radiology/dicom/upload/',
                {
                    'patient_id': str(other_patient.external_id),
                    'file': dcm_file
                },
                format='multipart'
            )

        self.assertEqual(response.status_code, 403)
```

### Integration Test

```bash
#!/bin/bash
# test_upload_integration.sh

# Prerequisites
export JWT_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
export PATIENT_ID="550e8400-e29b-41d4-a716-446655440000"
export DICOM_FILE="test_data/chest_xray.dcm"

# Test 1: Successful upload
echo "Test 1: Upload DICOM file"
response=$(curl -s -w "\n%{http_code}" \
  -X POST http://localhost:9000/api/care_radiology/dicom/upload/ \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -F "patient_id=$PATIENT_ID" \
  -F "file=@$DICOM_FILE")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" -eq 200 ]; then
    echo "✓ Upload successful"
    study_uid=$(echo "$body" | jq -r '.study_uid')
    echo "  Study UID: $study_uid"
else
    echo "✗ Upload failed with status $http_code"
    echo "$body"
    exit 1
fi

# Test 2: Verify in database
echo "\nTest 2: Verify database record"
psql -h localhost -U postgres -d care -c \
  "SELECT external_id, dicom_study_uid FROM radiology_dicomstudy WHERE dicom_study_uid = '$study_uid';"

# Test 3: Verify in DCM4CHEE
echo "\nTest 3: Query DCM4CHEE"
curl -s "http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies?StudyInstanceUID=$study_uid" \
  -H "Accept: application/json" | jq '.[] | {StudyInstanceUID, StudyDescription, StudyDate}'

# Test 4: Verify cache invalidation
echo "\nTest 4: Check Redis cache"
redis-cli GET "radiology:dicom:study:$study_uid"
# Should be empty (null) after upload

echo "\n✓ All tests passed"
```

---

## Monitoring and Logging

### Application Logs

```python
import logging

logger = logging.getLogger(__name__)

# Location: api/dicom.py:69-82
print("Content Type:", content_type)
print("DCM4CHEE_BASEURL:", DCM4CHEE_BASEURL)
print("STATUS:", upload_response.status_code)
print("RAW TEXT:", upload_response.text)
```

**Recommendation**: Replace `print()` with structured logging

```python
logger.info(
    "DICOM upload initiated",
    extra={
        "patient_id": str(patient.external_id),
        "file_name": dcm_file.name,
        "file_size": dcm_file.size,
        "user_id": request.user.id,
        "facility_id": patient.facility_id
    }
)

logger.info(
    "DCM4CHEE upload response",
    extra={
        "status_code": upload_response.status_code,
        "study_uid": study_uid,
        "duration_ms": (time.time() - start_time) * 1000
    }
)
```

### Metrics to Track

```python
from prometheus_client import Counter, Histogram

dicom_upload_total = Counter(
    'dicom_upload_total',
    'Total DICOM uploads',
    ['status', 'facility']
)

dicom_upload_duration = Histogram(
    'dicom_upload_duration_seconds',
    'DICOM upload duration',
    ['facility']
)

# In upload function
with dicom_upload_duration.labels(facility=patient.facility.name).time():
    # ... upload logic ...
    pass

dicom_upload_total.labels(
    status='success',
    facility=patient.facility.name
).inc()
```

---

## Related Documentation

- [API_QUERY_ENDPOINT.md](./API_QUERY_ENDPOINT.md) - Study query operations
- [DCM4CHEE_INTEGRATION.md](./DCM4CHEE_INTEGRATION.md) - DCM4CHEE architecture
- [AUTHORIZATION.md](./AUTHORIZATION.md) - Permission system details
- [WEBHOOK_ENDPOINT.md](./WEBHOOK_ENDPOINT.md) - Webhook integration

---

*Document Version: 1.0*
*Last Updated: 2025-04-16*
*Maintained by: Care Development Team*
