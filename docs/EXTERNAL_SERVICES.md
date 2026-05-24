# External Services Integration - Complete Technical Documentation

This document covers all external services integrated with the care_radiology plugin: OHIF Viewer, MinIO Storage, OpenLDAP, and Nginx Proxy.

---

## Table of Contents

1. [OHIF Viewer](#ohif-viewer)
2. [MinIO Object Storage](#minio-object-storage)
3. [OpenLDAP Directory](#openldap-directory)
4. [Nginx Reverse Proxy](#nginx-reverse-proxy)

---

# OHIF Viewer

## Overview

**OHIF** (Open Health Imaging Foundation) Viewer is a zero-footprint, web-based medical imaging viewer optimized for clinical use.

**Version**: v3.9.2
**Image**: `ohif/app:v3.9.2`
**Project**: https://github.com/OHIF/Viewers

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  OHIF Container (Port 3000)                                          │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Nginx Web Server                                              │ │
│  │  ────────────────────────────────────────────────────────────  │ │
│  │                                                                │ │
│  │  Document Root: /usr/share/nginx/html/                        │ │
│  │                                                                │ │
│  │  Files:                                                        │ │
│  │  ├── index.html          (Main HTML page)                     │ │
│  │  ├── app-config.js       (Configuration - MOUNTED)            │ │
│  │  ├── static/             (React app bundles)                  │ │
│  │  │   ├── js/                                                  │ │
│  │  │   ├── css/                                                 │ │
│  │  │   └── media/                                               │ │
│  │  └── ...                                                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Docker Configuration

### Container Specification

**docker-compose.radiology.yaml**:
```yaml
ohif:
  image: ohif/app:v3.9.2
  platform: linux/amd64
  ports:
    - "3000:80"
  volumes:
    - ./docker/ohif/app-config.js:/usr/share/nginx/html/app-config.js
```

**Platform**: `linux/amd64` required for macOS Apple Silicon (M1/M2)

### Volume Mount

**Purpose**: Override default OHIF configuration

**Source**: `docker/ohif/app-config.js` (host)
**Target**: `/usr/share/nginx/html/app-config.js` (container)

**Why Read-Only Mount?**:
- Configuration should not be modified by OHIF
- Prevents accidental changes
- Mount as read-only: `app-config.js:ro` (recommended)

---

## Configuration

### app-config.js Structure

**File**: `docker/ohif/app-config.js`

```javascript
window.config = {
  routerBasename: '/',
  extensions: [],
  modes: [],
  showStudyList: true,
  maxNumberOfWebWorkers: 4,
  showWarningMessageForCrossOrigin: false,
  showCPUFallbackMessage: false,
  strictZSpacingForVolumeViewport: false,

  // Data Sources Configuration
  dataSources: [
    {
      namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
      sourceName: 'dicomweb',
      configuration: {
        friendlyName: 'DCM4CHEE Archive',
        name: 'DCM4CHEE',

        // CRITICAL: Must be publicly accessible from browser
        wadoUriRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/wado',
        qidoRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',
        wadoRoot: 'http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',

        // Image loading options
        imageRendering: 'wadors',
        thumbnailRendering: 'wadors',
        enableStudyLazyLoad: true,

        // Support for bulk data
        supportsFuzzyMatching: false,
        supportsWildcard: true,

        // Optional: Custom headers (for authentication)
        // requestOptions: {
        //   headers: {
        //     'Authorization': 'Bearer <token>'
        //   }
        // }
      },
    },
  ],

  // Default Data Source
  defaultDataSourceName: 'dicomweb',
};
```

### Configuration Fields Explained

#### 1. `wadoUriRoot` (WADO-URI)

**Purpose**: Legacy DICOM retrieval endpoint

**Format**:
```
http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/wado
```

**Usage**:
```javascript
// OHIF constructs URL:
const url = `${wadoUriRoot}?requestType=WADO&studyUID=${studyUID}&seriesUID=${seriesUID}&objectUID=${instanceUID}`;
```

**When Used**: Fallback for older PACS systems

---

#### 2. `qidoRoot` (QIDO-RS)

**Purpose**: Query endpoint for study/series/instance metadata

**Format**:
```
http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs
```

**Usage**:
```javascript
// OHIF queries for studies:
GET ${qidoRoot}/studies?PatientID=MRN12345

// OHIF queries for series:
GET ${qidoRoot}/studies/${studyUID}/series

// OHIF queries for instances:
GET ${qidoRoot}/studies/${studyUID}/series/${seriesUID}/instances
```

**When Used**: Study list, metadata loading

---

#### 3. `wadoRoot` (WADO-RS)

**Purpose**: Modern DICOM retrieval endpoint

**Format**:
```
http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs
```

**Usage**:
```javascript
// OHIF retrieves frames:
GET ${wadoRoot}/studies/${studyUID}/series/${seriesUID}/instances/${instanceUID}/frames/1

// OHIF retrieves metadata:
GET ${wadoRoot}/studies/${studyUID}/metadata

// OHIF retrieves series:
GET ${wadoRoot}/studies/${studyUID}/series/${seriesUID}
```

**When Used**: Image display, viewport rendering

---

### Production Configuration

**File**: `docker/ohif/app-config.js` (Production)

```javascript
window.config = {
  dataSources: [
    {
      configuration: {
        friendlyName: 'Production PACS',

        // IMPORTANT: Use your public domain
        wadoUriRoot: 'https://pacs.yourhospital.com/dicomweb/dcm4chee-arc/aets/DCM4CHEE/wado',
        qidoRoot: 'https://pacs.yourhospital.com/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',
        wadoRoot: 'https://pacs.yourhospital.com/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs',

        // Enable authentication
        requestOptions: {
          headers: {
            'Authorization': `Bearer ${getJWTToken()}`
          }
        }
      },
    },
  ],
};

// Helper function to get JWT from Care frontend
function getJWTToken() {
  // Extract from localStorage, cookie, or URL parameter
  return localStorage.getItem('care_jwt_token');
}
```

---

## Viewer URL Patterns

### Opening a Study

**URL Format**:
```
http://localhost:32314/viewer?StudyInstanceUIDs=<study_uid>
```

**Example**:
```
http://localhost:32314/viewer?StudyInstanceUIDs=1.2.840.113619.2.55.3.2609.2.1.1
```

### Multiple Studies

**URL Format**:
```
http://localhost:32314/viewer?StudyInstanceUIDs=<uid1>,<uid2>,<uid3>
```

**Example**:
```
http://localhost:32314/viewer?StudyInstanceUIDs=1.2.840...1,1.2.840...2
```

### Study List View

**URL**:
```
http://localhost:32314/
```

**Behavior**: Shows all studies (queries QIDO-RS with no filters)

---

## Integration with Care Frontend

### React Component Example

```javascript
import React from 'react';

const DicomStudyViewer = ({ studyUid }) => {
  const openInOHIF = () => {
    const viewerUrl = `http://localhost:32314/viewer?StudyInstanceUIDs=${studyUid}`;
    window.open(viewerUrl, '_blank', 'width=1920,height=1080');
  };

  return (
    <button onClick={openInOHIF} className="btn btn-primary">
      View in OHIF Viewer
    </button>
  );
};

export default DicomStudyViewer;
```

### Study List Display

```javascript
const StudyList = ({ patientId }) => {
  const [studies, setStudies] = useState([]);

  useEffect(() => {
    // Fetch studies from Care API
    fetch(`/api/care_radiology/dicom/studies/?patientId=${patientId}`, {
      headers: {
        'Authorization': `Bearer ${getJWTToken()}`
      }
    })
      .then(res => res.json())
      .then(data => setStudies(data));
  }, [patientId]);

  return (
    <div className="study-list">
      {studies.map(study => (
        <div key={study.study_uid} className="study-card">
          <h3>{study.study_description}</h3>
          <p>Date: {new Date(study.study_date).toLocaleDateString()}</p>
          <p>Modalities: {study.study_modalities.join(', ')}</p>
          <button onClick={() => openInOHIF(study.study_uid)}>
            View Images
          </button>
        </div>
      ))}
    </div>
  );
};
```

---

## Image Loading Flow

```
Browser
  │
  │ 1. User clicks "View Study"
  ▼
http://localhost:32314/viewer?StudyInstanceUIDs=1.2.840...
  │
  │ 2. OHIF loads app-config.js
  ▼
OHIF React App
  │
  │ 3. Parse StudyInstanceUID from URL
  │ 4. Query metadata
  ▼
GET http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.2.840.../metadata
  │
  ▼
Nginx Proxy (Port 32314)
  │
  │ 5. auth_request /authenticate
  ▼
Care Backend (/api/care_radiology/dicom/authenticate/)
  │
  │ 6. Verify JWT token
  │ 7. Return 200 OK
  ▼
Nginx forwards to DCM4CHEE
  │
  ▼
DCM4CHEE (Port 8080)
  │
  │ 8. Query PostgreSQL for metadata
  │ 9. Return DICOM JSON
  ▼
OHIF receives metadata
  │
  │ 10. Parse series and instances
  │ 11. Request frames for display
  ▼
GET http://localhost:32314/dicomweb/.../frames/1
  │
  ▼
DCM4CHEE
  │
  │ 12. Retrieve DICOM from MinIO
  │ 13. Extract frame (decompress, convert)
  │ 14. Return JPEG image
  ▼
OHIF displays image in viewport
```

---

## Performance Optimization

### 1. Prefetching Strategy

**OHIF Configuration**:
```javascript
window.config = {
  dataSources: [
    {
      configuration: {
        // Lazy load study metadata (faster initial load)
        enableStudyLazyLoad: true,

        // Prefetch nearby frames
        prefetchPolicy: {
          enabled: true,
          maxImagesToPrefetch: 5,
          orderBy: 'closest'
        }
      }
    }
  ]
};
```

### 2. Web Workers

**Configuration**:
```javascript
window.config = {
  // Number of web workers for parallel image decoding
  maxNumberOfWebWorkers: 4,  // Match CPU cores
};
```

**Purpose**:
- Parallel JPEG/JPEG2000 decoding
- Non-blocking UI during image loading
- Utilizes multi-core CPUs

### 3. Viewport Caching

**Default Behavior**:
- OHIF caches decoded images in memory
- Max cache size: ~500MB (configurable)
- LRU eviction policy

**Tuning**:
```javascript
// Not directly configurable in app-config.js
// Set via Cornerstone3D configuration (advanced)
import { cache } from '@cornerstonejs/core';
cache.setMaxCacheSize(1024 * 1024 * 1024); // 1GB
```

---

## Troubleshooting

### Issue 1: OHIF Shows "No Data Sources Configured"

**Cause**: `app-config.js` not loaded or malformed

**Solution**:
```bash
# Check volume mount
docker inspect care_radiology-ohif-1 | grep Mounts

# Verify file exists in container
docker exec care_radiology-ohif-1 cat /usr/share/nginx/html/app-config.js

# Check for JavaScript syntax errors
node -c docker/ohif/app-config.js
```

---

### Issue 2: Images Not Loading (Infinite Spinner)

**Cause**: DICOMweb endpoints not reachable from browser

**Diagnosis**:
```bash
# Test QIDO-RS from browser console
fetch('http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs/studies')
  .then(r => r.json())
  .then(console.log);
```

**Common Errors**:
- CORS blocked: Check nginx CORS headers
- 401 Unauthorized: Authentication failing
- 502 Bad Gateway: DCM4CHEE down

**Solution**:
```bash
# Verify nginx is routing correctly
docker logs care_radiology-nginx-1

# Test DCM4CHEE directly
curl http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies
```

---

### Issue 3: CORS Errors

**Symptom**:
```
Access to fetch at 'http://localhost:8080/...' from origin 'http://localhost:32314'
has been blocked by CORS policy
```

**Solution**: Nginx already configured with CORS headers (see Nginx section)

**Verify**:
```bash
curl -I http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs/studies \
  -H "Origin: http://localhost:32314"
# Should include:
# Access-Control-Allow-Origin: *
```

---

# MinIO Object Storage

## Overview

**MinIO** is a high-performance, S3-compatible object storage system used to store DICOM image files.

**Protocol**: S3 API (AWS S3 compatible)
**Project**: https://min.io

---

## Architecture in care_radiology

```
┌─────────────────────────────────────────────────────────────────┐
│  MinIO Server (Standalone Mode)                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  S3 API (Port 9000)                                      │  │
│  │  ──────────────────────────────────────────────────────  │  │
│  │                                                          │  │
│  │  Endpoints:                                              │  │
│  │  - PUT    /dicom-bucket/{key}     (Upload object)       │  │
│  │  - GET    /dicom-bucket/{key}     (Download object)     │  │
│  │  - HEAD   /dicom-bucket/{key}     (Check existence)     │  │
│  │  - DELETE /dicom-bucket/{key}     (Remove object)       │  │
│  │  - GET    /dicom-bucket?list-type=2 (List objects)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Web Console (Port 9001)                                 │  │
│  │  ──────────────────────────────────────────────────────  │  │
│  │  - Bucket management                                     │  │
│  │  - Object browser                                        │  │
│  │  - Access policy configuration                           │  │
│  │  - Metrics and monitoring                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Storage:                                                        │
│  /data/                                                          │
│    └── dicom-bucket/                                             │
│          └── studies/                                            │
│                └── {StudyInstanceUID}/                           │
│                      └── series/                                 │
│                            └── {SeriesInstanceUID}/              │
│                                  └── {SOPInstanceUID}.dcm        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Installation (Local Development)

### Option 1: Docker (Recommended for care_radiology)

**docker-compose.yaml** (add to care_radiology stack):
```yaml
minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: minioadmin
    MINIO_ROOT_PASSWORD: minioadmin
  ports:
    - "9000:9000"   # S3 API
    - "9001:9001"   # Web Console
  volumes:
    - minio-data:/data

volumes:
  minio-data:
```

**Start**:
```bash
docker compose up -d minio
```

---

### Option 2: Homebrew (macOS)

```bash
# Install
brew install minio/stable/minio

# Start server
minio server /usr/local/var/minio

# Web Console: http://localhost:9001
# S3 API: http://localhost:9000
```

---

### Option 3: Binary Download

```bash
# Download
wget https://dl.min.io/server/minio/release/darwin-amd64/minio
chmod +x minio

# Start
./minio server /path/to/data
```

---

## Configuration for DCM4CHEE

### 1. Create Bucket

**Via Web Console** (http://localhost:9001):
1. Login (minioadmin / minioadmin)
2. Buckets → Create Bucket
3. Name: `dicom-bucket`
4. Click Create

**Via CLI** (`mc` - MinIO Client):
```bash
# Install mc
brew install minio/stable/mc

# Configure alias
mc alias set local http://localhost:9000 minioadmin minioadmin

# Create bucket
mc mb local/dicom-bucket

# Verify
mc ls local/
```

**Via AWS CLI**:
```bash
aws --endpoint-url http://localhost:9000 \
    s3 mb s3://dicom-bucket \
    --region us-east-1
```

---

### 2. Configure Access Policy

**Bucket Policy** (allow DCM4CHEE access):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": ["*"]
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": ["arn:aws:s3:::dicom-bucket/*"]
    },
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": ["*"]
      },
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::dicom-bucket"]
    }
  ]
}
```

**Apply via mc**:
```bash
mc anonymous set download local/dicom-bucket
mc anonymous set upload local/dicom-bucket
```

---

### 3. LDAP Configuration (DCM4CHEE)

**See**: [DCM4CHEE_INTEGRATION.md - LDAP Configuration](./DCM4CHEE_INTEGRATION.md#ldap-configuration)

**bucketconfig.ldif**:
```ldif
dn: dcmStorageID=minio,dicomDeviceName=dcm4chee-arc,...
dcmProperty: endpoint=http://minio:9000
dcmProperty: accessKey=minioadmin
dcmProperty: secretKey=minioadmin
dcmProperty: pathStyleAccess=true
```

---

## Storage Structure

### Object Key Format

```
studies/{StudyInstanceUID}/series/{SeriesInstanceUID}/{SOPInstanceUID}.dcm
```

### Example

**Study**: `1.2.840.113619.2.55.3.2609.2.1.1`
**Series 1**: `1.2.840.113619.2.55.3.2609.2.2.1` (2 instances)
**Series 2**: `1.2.840.113619.2.55.3.2609.2.2.2` (3 instances)

**Object Keys**:
```
studies/1.2.840.113619.2.55.3.2609.2.1.1/series/1.2.840.113619.2.55.3.2609.2.2.1/1.2.840.113619.2.55.3.2609.2.3.1.dcm
studies/1.2.840.113619.2.55.3.2609.2.1.1/series/1.2.840.113619.2.55.3.2609.2.2.1/1.2.840.113619.2.55.3.2609.2.3.2.dcm
studies/1.2.840.113619.2.55.3.2609.2.1.1/series/1.2.840.113619.2.55.3.2609.2.2.2/1.2.840.113619.2.55.3.2609.2.3.3.dcm
studies/1.2.840.113619.2.55.3.2609.2.1.1/series/1.2.840.113619.2.55.3.2609.2.2.2/1.2.840.113619.2.55.3.2609.2.3.4.dcm
studies/1.2.840.113619.2.55.3.2609.2.1.1/series/1.2.840.113619.2.55.3.2609.2.2.2/1.2.840.113619.2.55.3.2609.2.3.5.dcm
```

**File Size**: 1MB - 50MB per DICOM file (typical)

---

## S3 API Operations

### PUT Object (Upload)

```bash
aws --endpoint-url http://localhost:9000 \
  s3 cp sample.dcm \
  s3://dicom-bucket/studies/1.2.840.../series/1.2.840.../1.2.840....dcm
```

**Response**:
```
ETag: "5d41402abc4b2a76b9719d911017c592"
```

---

### GET Object (Download)

```bash
aws --endpoint-url http://localhost:9000 \
  s3 cp \
  s3://dicom-bucket/studies/1.2.840.../series/1.2.840.../1.2.840....dcm \
  downloaded.dcm
```

---

### HEAD Object (Check Existence)

```bash
aws --endpoint-url http://localhost:9000 \
  s3api head-object \
  --bucket dicom-bucket \
  --key studies/1.2.840.../...dcm
```

**Response**:
```json
{
  "AcceptRanges": "bytes",
  "LastModified": "2025-04-16T10:30:45+00:00",
  "ContentLength": 1048576,
  "ETag": "\"5d41402abc4b2a76b9719d911017c592\"",
  "ContentType": "application/octet-stream"
}
```

---

### LIST Objects

```bash
aws --endpoint-url http://localhost:9000 \
  s3 ls s3://dicom-bucket/studies/1.2.840.../
```

**Response**:
```
                           PRE series/
```

---

## Production Configuration

### Distributed Mode (High Availability)

**4-Node Cluster**:
```bash
# Node 1
minio server http://node{1...4}/data{1...4} --console-address ":9001"

# Node 2
minio server http://node{1...4}/data{1...4} --console-address ":9001"

# Node 3
minio server http://node{1...4}/data{1...4} --console-address ":9001"

# Node 4
minio server http://node{1...4}/data{1...4} --console-address ":9001"
```

**Benefits**:
- Horizontal scalability
- Automatic replication (erasure coding)
- High availability (node failures tolerated)

---

### Lifecycle Management

**Bucket Lifecycle Policy**:
```json
{
  "Rules": [
    {
      "ID": "TransitionToArchive",
      "Status": "Enabled",
      "Prefix": "studies/",
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    },
    {
      "ID": "DeleteOldStudies",
      "Status": "Enabled",
      "Prefix": "studies/",
      "Expiration": {
        "Days": 2555
      }
    }
  ]
}
```

**Apply**:
```bash
aws --endpoint-url http://localhost:9000 \
  s3api put-bucket-lifecycle-configuration \
  --bucket dicom-bucket \
  --lifecycle-configuration file://lifecycle.json
```

---

### Encryption at Rest

**Server-Side Encryption (SSE-S3)**:
```bash
# Enable default encryption
aws --endpoint-url http://localhost:9000 \
  s3api put-bucket-encryption \
  --bucket dicom-bucket \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

**Effect**: All new objects automatically encrypted

---

### Monitoring

**Prometheus Metrics**:

**Endpoint**: `http://localhost:9000/minio/v2/metrics/cluster`

**Key Metrics**:
- `minio_bucket_objects_size_bytes{bucket="dicom-bucket"}`: Total size
- `minio_bucket_objects_count{bucket="dicom-bucket"}`: Object count
- `minio_s3_requests_total`: API request count
- `minio_s3_requests_errors_total`: Error count

**Prometheus Config**:
```yaml
scrape_configs:
  - job_name: 'minio'
    metrics_path: /minio/v2/metrics/cluster
    static_configs:
      - targets: ['localhost:9000']
```

---

# OpenLDAP Directory

## Overview

**OpenLDAP** is used by DCM4CHEE to store configuration (storage descriptors, AE titles, network settings).

**Version**: 2.6.8 (via `dcm4che/slapd-dcm4chee:2.6.8-34.1`)
**Purpose**: Configuration database for DCM4CHEE

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  OpenLDAP Container (Port 389)                                    │
│  ──────────────────────────────────────────────────────────────  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  slapd (OpenLDAP Server)                                   │  │
│  │  ────────────────────────────────────────────────────────  │  │
│  │                                                            │  │
│  │  Base DN: dc=dcm4che,dc=org                               │  │
│  │  Admin DN: cn=admin,dc=dcm4che,dc=org                     │  │
│  │  Password: dcm4chee                                        │  │
│  │                                                            │  │
│  │  Directory Structure:                                      │  │
│  │  dc=dcm4che,dc=org                                         │  │
│  │  ├── cn=DICOM Configuration                               │  │
│  │  │   └── cn=Devices                                       │  │
│  │  │       └── dicomDeviceName=dcm4chee-arc                 │  │
│  │  │           ├── Storage Descriptors                      │  │
│  │  │           │   └── dcmStorageID=minio                   │  │
│  │  │           ├── Network AEs                              │  │
│  │  │           │   └── dicomAETitle=DCM4CHEE                │  │
│  │  │           └── Transfer Capabilities                    │  │
│  │  └── ou=People (users)                                    │  │
│  │  └── ou=Groups (roles)                                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Storage: /var/lib/ldap/                                         │
└───────────────────────────────────────────────────────────────────┘
```

---

## Docker Configuration

```yaml
ldap:
  image: dcm4che/slapd-dcm4chee:2.6.8-34.1
  ports:
    - "3890:389"
```

**Default Credentials**:
- Admin DN: `cn=admin,dc=dcm4che,dc=org`
- Password: `dcm4chee`

---

## LDAP Operations

### Search (Query)

```bash
ldapsearch -x \
  -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 \
  -W \
  -b "cn=DICOM Configuration,dc=dcm4che,dc=org" \
  "(objectClass=*)"
```

**Explanation**:
- `-x`: Simple authentication
- `-D`: Bind DN (admin user)
- `-H`: LDAP URL
- `-W`: Prompt for password
- `-b`: Base DN (search starting point)

---

### Modify (Update)

**LDIF File** (`modify.ldif`):
```ldif
dn: dcmStorageID=minio,dicomDeviceName=dcm4chee-arc,...
changetype: modify
replace: dcmProperty
dcmProperty: endpoint=http://minio:9000
dcmProperty: accessKey=NEW_ACCESS_KEY
dcmProperty: secretKey=NEW_SECRET_KEY
```

**Apply**:
```bash
ldapmodify -x \
  -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 \
  -W \
  -f modify.ldif
```

---

### Add (Create)

**LDIF File** (`add.ldif`):
```ldif
dn: dcmStorageID=s3-archive,dicomDeviceName=dcm4chee-arc,...
changetype: add
objectClass: dcmStorage
dcmStorageID: s3-archive
dcmURI: s3://archive-bucket
dcmInstanceAvailability: NEARLINE
```

**Apply**:
```bash
ldapadd -x \
  -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 \
  -W \
  -f add.ldif
```

---

### Delete

```bash
ldapdelete -x \
  -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 \
  -W \
  "dcmStorageID=s3-archive,dicomDeviceName=dcm4chee-arc,..."
```

---

## DCM4CHEE Integration

### How DCM4CHEE Uses LDAP

1. **Startup**:
   ```
   DCM4CHEE starts → Connect to LDAP → Load configuration →
   Read storage descriptors → Initialize storage providers →
   Ready to accept DICOM
   ```

2. **Runtime**:
   ```
   DICOM upload → DCM4CHEE receives → Parse Study UID →
   Query LDAP for storage config → Get MinIO endpoint →
   Store file in MinIO → Update metadata in PostgreSQL
   ```

3. **Configuration Changes**:
   ```
   Admin modifies LDAP → DCM4CHEE watches for changes →
   Reload configuration → Apply new settings (hot reload)
   ```

---

### Storage Configuration Details

**Entry**:
```
dn: dcmStorageID=minio,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
```

**Attributes**:
| Attribute | Value | Description |
|-----------|-------|-------------|
| `dcmStorageID` | minio | Unique identifier |
| `dcmURI` | s3://dicom-bucket | S3 bucket URI |
| `dcmDigestAlgorithm` | MD5 | Checksum algorithm |
| `dcmInstanceAvailability` | ONLINE | Storage tier |
| `dcmStorageThreshold` | 0 | No threshold (always use) |
| `dcmProperty` | endpoint=http://minio:9000 | MinIO endpoint |
| `dcmProperty` | accessKey=minioadmin | S3 access key |
| `dcmProperty` | secretKey=minioadmin | S3 secret key |
| `dcmProperty` | pathStyleAccess=true | Use path-style URLs |

---

## Troubleshooting

### Issue: DCM4CHEE Can't Connect to LDAP

**Symptoms**:
```
DCM4CHEE log: "Waiting for LDAP at ldap:389..."
```

**Solution**:
```bash
# Check LDAP is running
docker ps | grep ldap

# Test connection from DCM4CHEE container
docker exec care_radiology-arc-1 nc -zv ldap 389
```

---

### Issue: Storage Configuration Not Applied

**Symptoms**: DICOM uploads fail with storage error

**Diagnosis**:
```bash
# Query LDAP for storage config
ldapsearch -x -D "cn=admin,dc=dcm4che,dc=org" \
  -H ldap://localhost:3890 -W \
  -b "dcmStorageID=minio,..." \
  "(objectClass=dcmStorage)"
```

**Solution**: Re-import `bucketconfig.ldif`

---

# Nginx Reverse Proxy

## Overview

**Nginx** acts as a reverse proxy, routing requests between OHIF, DCM4CHEE, and Care backend, while handling authentication.

**Version**: nginx:alpine
**Configuration**: `docker/nginx-proxy/nginx.conf`

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Nginx Container (Port 32314 → Port 80)                          │
│  ──────────────────────────────────────────────────────────────  │
│                                                                   │
│  Routes:                                                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  / → OHIF Viewer (ohif:80)                                 │  │
│  │      - Public access                                       │  │
│  │      - Static files (React app)                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  /dicomweb/* → DCM4CHEE (arc:8080)                         │  │
│  │      - Authenticated access (auth_request)                 │  │
│  │      - DICOMweb API (QIDO, WADO, STOW)                     │  │
│  │      - CORS headers for OPTIONS                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  /authenticate (internal) → Care (host.docker.internal:9000)│  │
│  │      - JWT verification endpoint                           │  │
│  │      - Called via auth_request subrequest                  │  │
│  └────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

---

## Configuration File

**File**: `docker/nginx-proxy/nginx.conf`

```nginx
worker_processes 1;

events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;

    sendfile        on;
    keepalive_timeout  65;

    server {
        listen       80;
        server_name  localhost;
        client_max_body_size 100M;

        # OHIF Viewer
        location / {
            if ($request_method = OPTIONS) {
                return 204;
            }

            proxy_pass http://ohif:80;
            proxy_set_header HOST $host;
            proxy_set_header X-Real-IP $remote_addr;
            rewrite /ohif(.*) $1 break;
        }

        # DCM4CHEE Server
        location /dicomweb/ {
            if ($request_method = OPTIONS) {
                add_header 'Access-Control-Allow-Origin' '*' always;
                add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
                add_header 'Access-Control-Allow-Headers' '*' always;
                add_header 'Access-Control-Allow-Credentials' 'true' always;
                return 204;
            }

            auth_request /authenticate;

            # Don't pass auth headers to DCM4CHE
            proxy_set_header authorization "";
            proxy_set_header Authorization "";

            proxy_pass http://arc:8080;
            proxy_set_header HOST $host;
            proxy_set_header X-Real-IP $remote_addr;
            rewrite /dicomweb(.*) $1 break;
        }

        # Authentication Endpoint
        location = /authenticate {
            internal;
            proxy_pass http://host.docker.internal:9000/api/care_radiology/dicom/authenticate/;
            proxy_set_header HOST $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header Accept application/json;
            proxy_pass_request_body off;
            proxy_set_header Content-Length "";
        }
    }
}
```

---

## Configuration Breakdown

### 1. OHIF Location Block

```nginx
location / {
    proxy_pass http://ohif:80;
    proxy_set_header HOST $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

**Purpose**: Serve OHIF viewer

**Behavior**:
- All requests to `/` routed to OHIF
- No authentication required
- Static file serving

**Example**:
```
Browser: GET http://localhost:32314/
Nginx:   GET http://ohif:80/
```

---

### 2. DICOMweb Location Block

```nginx
location /dicomweb/ {
    auth_request /authenticate;

    proxy_set_header authorization "";
    proxy_set_header Authorization "";

    proxy_pass http://arc:8080;
    rewrite /dicomweb(.*) $1 break;
}
```

**Purpose**: Proxy DICOMweb API to DCM4CHEE with authentication

**Key Features**:
- `auth_request /authenticate`: Validates JWT before proxying
- Strips Authorization header (don't send JWT to DCM4CHEE)
- URL rewriting: `/dicomweb/rs/studies` → `/rs/studies`

**Authentication Flow**:
```
1. Browser: GET /dicomweb/rs/studies
   Header: Authorization: Bearer <JWT>

2. Nginx: Internal subrequest to /authenticate
   Passes: Authorization header, Host, X-Real-IP

3. Care Backend: Validates JWT
   Returns: 200 OK (if valid) or 401/403 (if invalid)

4. Nginx: If 200, proxy to DCM4CHEE
   If error, return 401/403 to browser

5. DCM4CHEE: Receives request WITHOUT Authorization header
   Returns: DICOM data

6. Browser: Receives DICOM data
```

**Example**:
```
Browser: GET http://localhost:32314/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs/studies
         Authorization: Bearer eyJhbGciOiJIUzI1NiI...

Nginx:   Internal subrequest to /authenticate (200 OK)
Nginx:   GET http://arc:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies
         (No Authorization header)

DCM4CHEE: Returns DICOM JSON
```

---

### 3. Authentication Location Block

```nginx
location = /authenticate {
    internal;
    proxy_pass http://host.docker.internal:9000/api/care_radiology/dicom/authenticate/;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
}
```

**Purpose**: JWT verification endpoint (subrequest only)

**Key Features**:
- `internal`: Only accessible via nginx subrequests (not from browser)
- `proxy_pass_request_body off`: Don't send body (only headers)
- Forwards Authorization header to Care backend

**Care Backend Endpoint**:
```python
@action(detail=False, methods=["get"], url_path="authenticate")
def authenticate(self, _):
    return Response(status=200)
```

**Note**: Actual JWT validation done by Care's middleware (JWTAuthentication)

---

### 4. CORS Handling

```nginx
if ($request_method = OPTIONS) {
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' '*' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;
    return 204;
}
```

**Purpose**: Handle CORS preflight requests

**Why Needed?**:
- OHIF makes cross-origin requests to DCM4CHEE
- Browser sends OPTIONS request before GET/POST
- Must respond with CORS headers

**Flow**:
```
1. Browser: OPTIONS /dicomweb/rs/studies
   Origin: http://localhost:32314

2. Nginx: Return 204 No Content
   Access-Control-Allow-Origin: *
   Access-Control-Allow-Methods: GET, POST, OPTIONS
   Access-Control-Allow-Headers: *

3. Browser: Actual request (GET /dicomweb/rs/studies)
```

---

### 5. Client Max Body Size

```nginx
client_max_body_size 100M;
```

**Purpose**: Allow large DICOM uploads (up to 100MB)

**Default**: 1MB (too small for DICOM)

**Recommendation**: Increase to 500MB for CT/MRI studies

---

## Production Configuration

```nginx
http {
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

    # Connection limiting
    limit_conn_zone $binary_remote_addr zone=addr:10m;

    server {
        listen       443 ssl http2;
        server_name  pacs.yourhospital.com;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        # Rate limiting
        limit_req zone=api_limit burst=20 nodelay;
        limit_conn addr 10;

        # Security headers
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "SAMEORIGIN" always;

        # Logging
        access_log /var/log/nginx/pacs_access.log;
        error_log /var/log/nginx/pacs_error.log;

        # ... location blocks ...
    }
}
```

---

## Monitoring

### Access Logs

```bash
docker exec care_radiology-nginx-1 tail -f /var/log/nginx/access.log
```

**Format**:
```
192.168.1.100 - - [16/Apr/2025:10:30:45 +0000] "GET /dicomweb/rs/studies HTTP/1.1" 200 5432 "-" "OHIF Viewer"
```

---

### Error Logs

```bash
docker exec care_radiology-nginx-1 tail -f /var/log/nginx/error.log
```

**Common Errors**:
- `auth_request failed (401)`: JWT invalid
- `upstream timed out (110)`: DCM4CHEE slow/down
- `client intended to send too large body (413)`: File > client_max_body_size

---

## Troubleshooting

### Issue: 401 Unauthorized on DICOM Requests

**Cause**: JWT not sent or invalid

**Diagnosis**:
```bash
# Check auth endpoint directly
curl -H "Authorization: Bearer <JWT>" \
  http://localhost:9000/api/care_radiology/dicom/authenticate/
# Should return 200 OK
```

**Solution**: Verify JWT is valid and not expired

---

### Issue: 502 Bad Gateway

**Cause**: Upstream service (ohif, arc, care) unreachable

**Diagnosis**:
```bash
# Check services are running
docker ps

# Test connectivity
docker exec care_radiology-nginx-1 nc -zv arc 8080
docker exec care_radiology-nginx-1 nc -zv ohif 80
docker exec care_radiology-nginx-1 nc -zv host.docker.internal 9000
```

---

### Issue: CORS Errors

**Cause**: Missing CORS headers

**Solution**: Verify OPTIONS handling in nginx.conf

**Test**:
```bash
curl -X OPTIONS http://localhost:32314/dicomweb/rs/studies \
  -H "Origin: http://localhost:32314" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization" \
  -v
# Should return 204 with CORS headers
```

---

## Related Documentation

- [API_UPLOAD_ENDPOINT.md](./API_UPLOAD_ENDPOINT.md) - Upload API flow
- [API_QUERY_ENDPOINT.md](./API_QUERY_ENDPOINT.md) - Query API flow
- [DCM4CHEE_INTEGRATION.md](./DCM4CHEE_INTEGRATION.md) - DCM4CHEE details
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture

---

*Document Version: 1.0*
*Last Updated: 2025-04-16*
*Maintained by: Care Development Team*
