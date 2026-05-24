# Radiology Plugin - Deployment Sequence

This document explains the **exact order** in which components must be deployed and **why** this sequence matters.

## ⚠️ Critical: Order Matters!

The radiology plugin has strict dependencies between components. Deploying out of order **will fail**.

## Deployment Flow Diagram

```
1. Secrets & Config → 2. Storage → 3. MinIO Bucket
                                          ↓
                                    4. LDAP (wait ready)
                                          ↓
                                    5. DB Schema (wait complete)
                                          ↓
                                    6. DB Permissions
                                          ↓
                                    7. DCM4CHEE (wait ready)
                                          ↓
                                    8. MinIO LDAP Config
                                          ↓
                                    9. Viewers (OHIF + Nginx)
                                          ↓
                                    10. Ingress
```

## Step-by-Step Deployment

### Step 1: Secrets & Configuration

**Files:** `01-secrets.yaml`, `02-configmap.yaml`

**Why First:**
- All subsequent deployments reference these configurations
- Must exist before any pod starts

**Commands:**
```bash
kubectl apply -f 01-secrets.yaml
kubectl apply -f 02-configmap.yaml
```

**Verification:**
```bash
kubectl get secret radiology-secrets -n care
kubectl get configmap radiology-config -n care
```

---

### Step 2: Persistent Storage

**Files:** `03-pvc.yaml`

**Why Now:**
- PVCs must be created before pods that mount them
- K3s needs time to provision volumes

**Commands:**
```bash
kubectl apply -f 03-pvc.yaml
```

**Verification:**
```bash
kubectl get pvc -n care | grep radiology
# Status should be "Bound"
```

---

### Step 3: Initialize MinIO Bucket

**Files:** `00-init-dicom-bucket.yaml`

**Why Now:**
- Creates `dicom-bucket` in existing MinIO
- Must exist before configuring DCM4CHEE storage
- Independent of other radiology components

**Commands:**
```bash
kubectl apply -f 00-init-dicom-bucket.yaml
kubectl wait --for=condition=complete job/radiology-init-minio -n care --timeout=120s
```

**Verification:**
```bash
kubectl logs job/radiology-init-minio -n care
# Should show: "DICOM bucket setup complete!"
```

---

### Step 4: Deploy LDAP

**Files:** `04-ldap.yaml`

**Why Now:**
- DCM4CHEE requires LDAP for configuration storage
- Uses pre-configured `dcm4che/slapd-dcm4chee:2.6.8-34.1` image
- Contains default DCM4CHEE device configuration

**Commands:**
```bash
kubectl apply -f 04-ldap.yaml
kubectl wait --for=condition=ready pod -l component=ldap -n care --timeout=120s
```

**Verification:**
```bash
kubectl get pods -n care -l component=ldap
# Should be Running 1/1
```

**Critical:** DCM4CHEE will fail to start if LDAP is not ready!

---

### Step 5: Initialize Database Schema

**Files:** `11-init-db-schema.yaml`

**Why Now:**
- DCM4CHEE requires DICOM tables to exist
- Downloads SQL scripts from public GitHub repository
- Creates tables, indexes, and foreign keys

**Commands:**
```bash
kubectl apply -f 11-init-db-schema.yaml
kubectl wait --for=condition=complete job/radiology-init-db-schema -n care --timeout=180s
```

**Verification:**
```bash
kubectl logs job/radiology-init-db-schema -n care
# Should show: "Database schema initialization complete!"
```

**What It Does:**
1. Downloads SQL scripts from `10bedicu/care_radiology` repository
2. Creates sequences and tables (`10_create-psql.sql`)
3. Creates foreign key indexes (`20_create-fk-index.sql`)
4. Creates case-insensitive indexes (`30_create-case-insensitive-index.sql`)

---

### Step 6: Grant Database Permissions

**Why Now:**
- Tables are owned by `postgres` superuser
- DCM4CHEE connects as `care` user
- Need to grant permissions before DCM4CHEE starts

**Commands:**
```bash
kubectl exec postgres-care-1 -n care -- \
  psql -U postgres -d dicom -c \
  "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO care; \
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO care; \
   GRANT ALL PRIVILEGES ON SCHEMA public TO care;"
```

**Verification:**
```bash
kubectl exec postgres-care-1 -n care -- \
  psql -U postgres -d dicom -c "\dt" | grep study
# Should show study, series, instance tables
```

---

### Step 7: Deploy DCM4CHEE

**Files:** `05-dcm4chee.yaml`

**Why Now:**
- All dependencies are ready:
  - ✓ LDAP has device configuration
  - ✓ Database has schema
  - ✓ Database permissions granted
  - ✓ MinIO bucket exists

**Commands:**
```bash
kubectl apply -f 05-dcm4chee.yaml
kubectl wait --for=condition=ready pod -l component=dcm4chee -n care --timeout=300s
```

**Wait Time:** 2-3 minutes for WildFly to start and deploy applications

**Verification:**
```bash
# Check deployment succeeded
kubectl exec deployment/radiology-dcm4chee -n care -- \
  ls -la /opt/wildfly/standalone/deployments/ | grep deployed

# Should show:
# dcm4chee-arc-ear-5.34.1-psql.ear.deployed
# dcm4chee-arc-ui2-5.34.1.war.deployed
```

**If Failed:**
```bash
# Check failure reason
kubectl exec deployment/radiology-dcm4chee -n care -- \
  cat /opt/wildfly/standalone/deployments/dcm4chee-arc-ear-5.34.1-psql.ear.failed
```

**Common Failures:**
- `Invalid Credentials` → Check LDAP passwords match
- `Device not found` → Check ARCHIVE_DEVICE_NAME = `dcm4chee-arc`
- `Permission denied for table` → Run Step 6 again

---

### Step 8: Configure MinIO Storage in LDAP

**Why Now:**
- DCM4CHEE is running but using default storage
- Need to update LDAP to point to MinIO bucket
- Modifies existing LDAP entry

**Commands:**
```bash
# Get MinIO credentials
MINIO_KEY=$(kubectl get secret care-secrets -n care -o jsonpath='{.data.BUCKET_KEY}' | base64 -d)
MINIO_SECRET=$(kubectl get secret care-secrets -n care -o jsonpath='{.data.BUCKET_SECRET}' | base64 -d)

# Create LDIF
cat > /tmp/bucketconfig.ldif <<EOF
dn: dcmStorageID=fs1,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
changetype: modify
replace: dcmURI
dcmURI: jclouds:s3:http://minio:9000
-
add: dcmProperty
dcmProperty: container=dicom-bucket
dcmProperty: containerExists=true
dcmProperty: endpoint=http://minio:9000
dcmProperty: credential=$MINIO_SECRET
dcmProperty: identity=$MINIO_KEY
dcmProperty: jclouds.relax-hostname=true
dcmProperty: jclouds.s3.path-style-access=true
dcmProperty: jclouds.s3.virtual-host-buckets=false
dcmProperty: jclouds.strip-expect-header=true
dcmProperty: jclouds.trust-all-certs=true
dcmProperty: streamingUpload=false
-
EOF

# Apply to LDAP
LDAP_POD=$(kubectl get pod -n care -l component=ldap -o jsonpath='{.items[0].metadata.name}')
kubectl cp /tmp/bucketconfig.ldif care/$LDAP_POD:/tmp/bucketconfig.ldif
kubectl exec deployment/radiology-ldap -n care -- \
  ldapmodify -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w secret -f /tmp/bucketconfig.ldif
```

**Verification:**
```bash
# Test DICOM upload will now store in MinIO
```

---

### Step 9: Deploy Viewers

**Files:** `06-ohif.yaml`, `07-nginx.yaml`

**Why Now:**
- DCM4CHEE is ready to serve DICOM data
- OHIF needs to connect to DCM4CHEE via Nginx proxy

**Commands:**
```bash
kubectl apply -f 06-ohif.yaml
kubectl wait --for=condition=ready pod -l component=ohif -n care --timeout=120s

kubectl apply -f 07-nginx.yaml
kubectl wait --for=condition=ready pod -l component=nginx -n care --timeout=120s
```

**Verification:**
```bash
kubectl get pods -n care -l app=care-radiology
# All pods should be Running
```

---

### Step 10: Deploy Ingress

**Files:** `08-ingress.yaml`

**Why Last:**
- All backend services must be ready
- Ingress routes external traffic to services
- Requires DNS configuration to work

**Commands:**
```bash
kubectl apply -f 08-ingress.yaml
```

**Verification:**
```bash
kubectl get ingress -n care
# Should show radiology-ohif and radiology-admin
```

---

## Final Verification

After all steps complete:

```bash
# 1. Check all pods
kubectl get pods -n care -l app=care-radiology

# Expected:
# radiology-dcm4chee-xxx   1/1   Running
# radiology-ldap-xxx       1/1   Running
# radiology-nginx-xxx      1/1   Running (2 replicas)
# radiology-ohif-xxx       1/1   Running (2 replicas)

# 2. Test DCM4CHEE API
kubectl exec deployment/radiology-dcm4chee -n care -- \
  curl -s http://localhost:8080/dcm4chee-arc/aets | grep DCM4CHEE

# 3. Test DICOM endpoint
kubectl exec deployment/radiology-dcm4chee -n care -- \
  curl -s http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies

# Should return: [] (empty array, no studies yet)
```

---

## Why This Order?

### Dependency Chain

1. **Secrets/Config** → Everything depends on these
2. **Storage** → Pods need PVCs before starting
3. **MinIO Bucket** → Must exist before LDAP configuration
4. **LDAP** → DCM4CHEE reads device config from here
5. **DB Schema** → DCM4CHEE needs DICOM tables
6. **DB Permissions** → DCM4CHEE user needs access
7. **DCM4CHEE** → Core PACS server
8. **MinIO LDAP Config** → Tells DCM4CHEE where to store images
9. **Viewers** → Connect to ready DCM4CHEE
10. **Ingress** → Exposes ready services

### What Happens If You Skip Steps?

| Skip Step | Result |
|-----------|--------|
| LDAP not ready | DCM4CHEE: `Connection refused` |
| DB schema missing | DCM4CHEE: `relation "study" does not exist` |
| DB permissions missing | DCM4CHEE: `permission denied for table study` |
| Wrong device name | DCM4CHEE: `Device with specified name not found` |
| MinIO not configured | DICOM uploads fail, images not stored |

---

## Automated Deployment

Use `deploy.sh` to run all steps automatically:

```bash
cd k3s/care/k8s/radiology
./deploy.sh
```

The script:
- ✓ Checks prerequisites
- ✓ Runs all steps in correct order
- ✓ Waits for each component to be ready
- ✓ Verifies deployment success
- ✓ Prints access URLs

---

## Troubleshooting Deployment Order Issues

### DCM4CHEE Won't Start

```bash
# Check logs for specific error
kubectl logs deployment/radiology-dcm4chee -n care | tail -100

# Check deployment failure
kubectl exec deployment/radiology-dcm4chee -n care -- \
  cat /opt/wildfly/standalone/deployments/*.failed
```

**Common Fixes:**
- `LDAP connection refused` → LDAP pod not ready, wait longer
- `ConfigurationNotFoundException` → LDAP image wrong or device name mismatch
- `Database error` → Schema not initialized, run Step 5
- `Permission denied` → Run Step 6 to grant permissions

### Start Over

```bash
# Delete in reverse order
kubectl delete -f 08-ingress.yaml
kubectl delete -f 07-nginx.yaml
kubectl delete -f 06-ohif.yaml
kubectl delete -f 05-dcm4chee.yaml
kubectl delete -f 04-ldap.yaml
kubectl delete -f 03-pvc.yaml
kubectl delete job radiology-init-minio radiology-init-db-schema -n care

# Start from Step 1
```

---

## Reference: Image Versions

**Critical:** Use these exact versions (from `docker-compose.radiology.yaml`):

```yaml
LDAP: dcm4che/slapd-dcm4chee:2.6.8-34.1
DCM4CHEE: dcm4che/dcm4chee-arc-psql:5.34.1
OHIF: ohif/app:v3.9.2
Nginx: nginx:alpine
```

**Why These Versions:**
- `slapd-dcm4chee:2.6.8-34.1` is pre-configured with DCM4CHEE defaults
- Newer tags may not exist in Docker Hub
- Older versions may have incompatibilities

---

## Summary

**Total Deployment Time:** ~10-15 minutes

**Steps That Wait:**
- LDAP ready: ~30 seconds
- DB schema: ~30 seconds
- DCM4CHEE ready: ~2-3 minutes
- OHIF ready: ~30 seconds

**Most Common Mistakes:**
1. ❌ Deploying DCM4CHEE before LDAP is ready
2. ❌ Not initializing database schema
3. ❌ Not granting database permissions
4. ❌ Using wrong device name in config
5. ❌ Skipping MinIO LDAP configuration

**Success Indicators:**
- ✅ No `.failed` files in DCM4CHEE deployments directory
- ✅ DCM4CHEE API returns AE titles
- ✅ DICOM endpoint returns `200 OK`
- ✅ All pods in `Running` state
