# Care Radiology Plugin - Testing Guide

This guide helps you test all radiology components using the provided Postman collection.

## Prerequisites

- Postman installed
- kubectl access to the K3s cluster
- All radiology pods running

## Quick Start

### 1. Import Postman Collection

1. Open Postman
2. Click **Import**
3. Select `Care-Radiology-Tests.postman_collection.json`
4. Collection will appear in your workspace

### 2. Set Up Port Forwarding

Open **separate terminal windows** for each service you want to test:

#### DCM4CHEE PACS (Main Service)
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-dcm4chee 8080:8080
```
**Local URL:** http://localhost:8080

#### DCM4CHEE Admin Console
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-dcm4chee 9990:9990
```
**Local URL:** http://localhost:9990
**Credentials:** admin / admin

#### OHIF Viewer
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-ohif 3000:80
```
**Local URL:** http://localhost:3000

#### Nginx Proxy
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-nginx 8888:80
```
**Local URL:** http://localhost:8888

#### LDAP Service
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-ldap 389:389
```
**Port:** 389

#### MinIO (Storage Backend)
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/minio 9000:9000 9001:9001
```
**API:** http://localhost:9000
**Console:** http://localhost:9001

---

## Testing Scenarios

### Test 1: Health Checks ✅

**Purpose:** Verify all services are running

1. Run: **01. Health Checks → DCM4CHEE - Health Check**
   - Expected: 200 OK with DCM4CHEE UI HTML

2. Run: **01. Health Checks → OHIF Viewer - Root**
   - Expected: 200 OK with OHIF viewer page

3. Run: **01. Health Checks → Nginx Proxy - Health**
   - Expected: 200 OK with health status

**Success Criteria:** All endpoints return 200 OK

---

### Test 2: DICOM Web - QIDO-RS (Query) 🔍

**Purpose:** Test DICOM query capabilities

1. Run: **02. DCM4CHEE - QIDO-RS → Search All Studies**
   - Expected: Empty array `[]` if no studies exist, or list of studies
   - Status: 200 OK

2. Run: **02. DCM4CHEE - QIDO-RS → Search Studies by Patient Name**
   - Modify query parameter `PatientName=*DOE*` to search
   - Expected: Filtered study list

3. Run: **02. DCM4CHEE - QIDO-RS → Search Studies by Date Range**
   - Expected: Studies within date range

**Success Criteria:** JSON responses with proper DICOM metadata

---

### Test 3: DICOM Web - WADO-RS (Retrieve) 📥

**Purpose:** Test DICOM retrieval capabilities

**Prerequisites:** At least one study must exist in PACS

1. First, get a Study UID from the query results
2. Update Collection Variables:
   - `StudyInstanceUID`: (e.g., `1.2.840.113619.2.1.1`)
   - `SeriesInstanceUID`: (e.g., `1.2.840.113619.2.1.2`)
   - `SOPInstanceUID`: (e.g., `1.2.840.113619.2.1.3`)

3. Run: **03. DCM4CHEE - WADO-RS → Retrieve Study Metadata**
   - Expected: Complete study metadata in JSON

4. Run: **03. DCM4CHEE - WADO-RS → Retrieve Instance**
   - Expected: Binary DICOM file

5. Run: **03. DCM4CHEE - WADO-RS → Retrieve Rendered Thumbnail**
   - Expected: JPEG image thumbnail

**Success Criteria:** Successful metadata and image retrieval

---

### Test 4: Admin APIs 🔧

**Purpose:** Test administrative functions

**Note:** Admin APIs require authentication

1. Run: **04. DCM4CHEE - Admin APIs → List AE Titles**
   - Expected: List containing "DCM4CHEE" AE title

2. Run: **04. DCM4CHEE - Admin APIs → Get Queue Status**
   - Expected: Queue status with counts

3. Run: **04. DCM4CHEE - Admin APIs → Get Device Configuration**
   - Requires Basic Auth: `admin / admin`
   - Expected: Complete device configuration

**Success Criteria:** Admin operations return expected data

---

### Test 5: LDAP Authentication 🔐

**Purpose:** Verify LDAP integration

**Using DCM4CHEE UI:**

1. Open browser: http://localhost:8080/dcm4chee-arc/ui2
2. You should see DCM4CHEE login page
3. LDAP authentication is working if you can access the UI

**Using ldapsearch (Terminal):**

```bash
# Port-forward LDAP first (in another terminal)
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-ldap 389:389

# Test LDAP connection
ldapsearch -x -H ldap://localhost:389 \
  -D "cn=admin,dc=dcm4che,dc=org" \
  -w admin \
  -b "dc=dcm4che,dc=org"
```

**Expected Output:** LDAP directory entries

**Success Criteria:** LDAP responds with directory data

---

### Test 6: Nginx Proxy 🚪

**Purpose:** Verify proxy routing and authentication

1. Run: **06. Nginx Proxy Tests → Nginx - Root**
   - Expected: Redirect or proxy to OHIF viewer

2. Run: **06. Nginx Proxy Tests → Nginx - DICOM Web Proxy**
   - Expected: Proxied QIDO-RS response
   - This proves Nginx → DCM4CHEE routing works

3. Run: **06. Nginx Proxy Tests → Nginx - Health Check**
   - Expected: Health status response

**Success Criteria:** All proxied requests work correctly

---

### Test 7: End-to-End Integration 🔄

**Purpose:** Test full stack integration

1. Run: **07. Integration Tests → OHIF Config**
   - Expected: JavaScript config pointing to correct endpoints
   - Verify `wadoUriRoot`, `qidoRoot`, `wadoRoot` settings

2. Run: **07. Integration Tests → Query via Nginx**
   - Tests: OHIF → Nginx → DCM4CHEE → PostgreSQL
   - Expected: Study list

3. Run: **07. Integration Tests → Verify MinIO Storage**
   - Tests: MinIO connectivity
   - Expected: Health OK response

**Success Criteria:** All layers communicate correctly

---

## Manual Browser Tests

### DCM4CHEE UI Console

```
URL: http://localhost:8080/dcm4chee-arc/ui2
```

**Features to Test:**
- ✅ Study list loads
- ✅ Search functionality
- ✅ Upload DICOM files
- ✅ View study details

### OHIF Viewer

```
URL: http://localhost:3000
```

**Features to Test:**
- ✅ Viewer loads without errors
- ✅ Study list appears
- ✅ Can open studies (if any exist)
- ✅ Image viewing tools work

### MinIO Console

```
URL: http://localhost:9001
Credentials: (check care-secrets)
```

**Features to Test:**
- ✅ Login works
- ✅ `dicom-storage` bucket exists
- ✅ Can view bucket contents
- ✅ Versioning is enabled

---

## Uploading Test DICOM Files

### Option 1: Via DCM4CHEE UI

1. Open: http://localhost:8080/dcm4chee-arc/ui2
2. Navigate to **Upload** section
3. Drag & drop DICOM files
4. Verify upload success

### Option 2: Via STOW-RS (Postman)

STOW-RS is not included in the collection but can be added. Example:

```bash
curl -X POST \
  http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies \
  -H "Content-Type: multipart/related; type=application/dicom" \
  --form 'file=@test.dcm'
```

### Option 3: Via DICOM C-STORE

Use DICOM tools like `dcm4che` or `storescu`:

```bash
# Port-forward DICOM port
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-dcm4chee 11112:11112

# Send DICOM file
storescu -c DCM4CHEE@localhost:11112 test.dcm
```

---

## Sample Test DICOM Files

Download free DICOM samples:

1. **Medical Connections:** https://www.dicomserver.co.uk/
2. **OsiriX Sample Data:** https://www.osirix-viewer.com/resources/dicom-image-library/
3. **Rubo Medical:** https://www.rubomedical.com/dicom_files/

---

## Troubleshooting

### Issue: Connection Refused

**Solution:** Ensure port-forward is running in another terminal

```bash
# Check if port is listening
lsof -i :8080
```

### Issue: Empty Study List

**Solution:** No DICOM studies uploaded yet. Upload test data first.

### Issue: 401 Unauthorized

**Solution:** Some endpoints require authentication

```
Username: admin
Password: admin
```

### Issue: LDAP Connection Failed

**Solution:** Check LDAP pod is running

```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get pods -n care -l component=ldap
```

### Issue: Slow Response

**Solution:** DCM4CHEE takes time to start. Wait 5-10 minutes after deployment.

Check logs:
```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig logs -f deployment/radiology-dcm4chee -n care
```

---

## All-in-One Port Forward Script

Create a script `start-port-forwards.sh`:

```bash
#!/bin/bash

KUBECONFIG=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig

# Function to create port-forward in background
forward_port() {
    local service=$1
    local ports=$2
    local name=$3

    echo "Starting port-forward for $name..."
    kubectl --kubeconfig=$KUBECONFIG port-forward -n care svc/$service $ports &
}

# Start all port-forwards
forward_port "radiology-dcm4chee" "8080:8080" "DCM4CHEE"
forward_port "radiology-dcm4chee" "9990:9990" "DCM4CHEE Admin"
forward_port "radiology-ohif" "3000:80" "OHIF Viewer"
forward_port "radiology-nginx" "8888:80" "Nginx Proxy"
forward_port "radiology-ldap" "389:389" "LDAP"
forward_port "minio" "9000:9000" "MinIO API"
forward_port "minio" "9001:9001" "MinIO Console"

echo "All port-forwards started!"
echo "Press Ctrl+C to stop all"

# Wait for Ctrl+C
wait
```

Make executable and run:
```bash
chmod +x start-port-forwards.sh
./start-port-forwards.sh
```

---

## Expected Test Results Summary

| Test Category | Expected Result | Status |
|---------------|----------------|--------|
| Health Checks | All 200 OK | ✅ |
| QIDO-RS Query | JSON study list | ✅ |
| WADO-RS Retrieve | DICOM data/images | ✅ |
| Admin APIs | Configuration data | ✅ |
| LDAP Auth | Directory entries | ✅ |
| Nginx Proxy | Successful proxying | ✅ |
| Integration | End-to-end success | ✅ |

---

## Next Steps After Testing

1. **Upload Real DICOM Data:** Use production DICOM files
2. **Configure TLS:** Set up HTTPS for production
3. **Update Domains:** Change from `.example.com` to real domains
4. **Set Up Monitoring:** Monitor PACS performance
5. **Configure Backups:** Back up PostgreSQL and MinIO regularly

---

## Support

For issues:
- Check pod logs: `kubectl --kubeconfig=... logs -f deployment/radiology-dcm4chee -n care`
- Check events: `kubectl --kubeconfig=... get events -n care --sort-by='.lastTimestamp'`
- Review README: `k3s/care/k8s/radiology/README.md`

---

**Happy Testing!** 🎉
