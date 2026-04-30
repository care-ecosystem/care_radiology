# DCM4CHEE Initialization Issue & Solution

## Problem

DCM4CHEE is failing to start with error:
```
ConfigurationNotFoundException
```

The main DCM4CHEE application (`dcm4chee-arc-ear-5.34.1-psql.ear`) fails to deploy because it cannot find its device configuration in LDAP.

## Root Cause

DCM4CHEE stores its configuration in LDAP. On first startup, it expects either:
1. An existing configuration in LDAP, OR
2. Ability to create initial configuration automatically

Currently, we have a fresh LDAP server with only the base DN (`dc=dcm4che,dc=org`) but no DCM4CHEE device configuration.

## Solution Options

### Option 1: Use Pre-configured LDAP with Sample Data (RECOMMENDED)

Use the official DCM4CHEE LDAP container that comes pre-configured:

```bash
# Replace the LDAP deployment with dcm4che's official LDAP image
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig set image deployment/radiology-ldap ldap=dcm4che/slapd-dcm4chee:2.6.11-34.1 -n care
```

This image includes:
- Pre-configured DICOM schema
- Default DCM4CHEE device configuration
- Proper indexes for DICOM attributes

### Option 2: Manual LDAP Initialization

1. **Download DCM4CHEE sample configuration:**
```bash
# Get the sample LDIF from DCM4CHEE
curl -O https://raw.githubusercontent.com/dcm4che/dcm4chee-arc-light/master/ldap/init-config.ldif
curl -O https://raw.githubusercontent.com/dcm4che/dcm4chee-arc-light/master/ldap/default-config.ldif
curl -O https://raw.githubusercontent.com/dcm4che/dcm4chee-arc-light/master/ldap/schema/dcm4che.ldif
```

2. **Apply the LDIF files:**
```bash
# Port-forward LDAP
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-ldap 389:389

# Apply schema and configuration
ldapadd -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w CHANGE_ME_LDAP_ADMIN_PASSWORD -f dcm4che.ldif
ldapadd -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w CHANGE_ME_LDAP_ADMIN_PASSWORD -f init-config.ldif
ldapadd -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w CHANGE_ME_LDAP_ADMIN_PASSWORD -f default-config.ldif
```

### Option 3: Use JSON Configuration (Simpler for Development)

Modify DCM4CHEE to use JSON-based configuration instead of LDAP:

1. Create a ConfigMap with JSON configuration
2. Mount it to DCM4CHEE
3. Set environment variable to use JSON config

---

## Recommended Quick Fix

Use the official dcm4che LDAP image which is pre-configured for DCM4CHEE:

```bash
#!/bin/bash
KUBECONFIG=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig

# Delete current LDAP data
kubectl --kubeconfig=$KUBECONFIG delete pod -n care -l component=ldap
kubectl --kubeconfig=$KUBECONFIG delete pvc radiology-ldap-data -n care

# Wait for deletion
sleep 10

# Update LDAP deployment to use dcm4che's official image
kubectl --kubeconfig=$KUBECONFIG set image deployment/radiology-ldap ldap=dcm4che/slapd-dcm4chee:2.6.11-34.1 -n care

# Recreate PVC
kubectl --kubeconfig=$KUBECONFIG apply -f k3s/care/k8s/radiology/03-pvc.yaml

# Wait for LDAP to be ready
kubectl --kubeconfig=$KUBECONFIG wait --for=condition=ready pod -l component=ldap -n care --timeout=300s

# Restart DCM4CHEE
kubectl --kubeconfig=$KUBECONFIG delete pod -n care -l component=dcm4chee

# Monitor DCM4CHEE startup
kubectl --kubeconfig=$KUBECONFIG logs -f deployment/radiology-dcm4chee -n care
```

## After Successful Startup

Once DCM4CHEE starts successfully, you'll need to configure MinIO storage:

```bash
# Port-forward LDAP
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-ldap 389:389

# Get MinIO credentials
MINIO_KEY=$(kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get secret care-secrets -n care -o jsonpath='{.data.BUCKET_KEY}' | base64 -d)
MINIO_SECRET=$(kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get secret care-secrets -n care -o jsonpath='{.data.BUCKET_SECRET}' | base64 -d)

# Apply MinIO storage configuration
cat <<EOF | ldapmodify -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w CHANGE_ME_LDAP_ADMIN_PASSWORD
dn: dcmStorageID=fs1,dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org
changetype: modify
replace: dcmURI
dcmURI: jclouds:s3:http://minio:9000
-
add: dcmProperty
dcmProperty: container=dicom-storage
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
```

## Verification

After DCM4CHEE starts successfully:

```bash
# Check deployment status
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig exec deployment/radiology-dcm4chee -n care -- ls -la /opt/wildfly/standalone/deployments/

# Should see:
# dcm4chee-arc-ear-5.34.1-psql.ear.deployed  (not .failed)
# dcm4chee-arc-ui2-5.34.1.war.deployed

# Test the API endpoint
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig exec deployment/radiology-dcm4chee -n care -- curl -s http://localhost:8080/dcm4chee-arc/aets

# Should return: ["DCM4CHEE"]
```

## Current Status

- ✅ LDAP is running with correct base DN (`dc=dcm4che,dc=org`)
- ✅ PostgreSQL has `dicom` database created
- ✅ MinIO has `dicom-storage` bucket created
- ❌ DCM4CHEE fails to start - needs LDAP configuration
- ✅ OHIF Viewer is running
- ✅ Nginx proxy is running

## Next Steps

1. **Choose one of the solutions above** (Option 1 recommended)
2. **Apply the fix**
3. **Wait for DCM4CHEE to start** (may take 5-10 minutes)
4. **Configure MinIO storage** in LDAP
5. **Test DICOM upload** via Postman or DCM4CHEE UI

---

**Note:** The official `dcm4che/slapd-dcm4chee` image is the easiest solution as it's specifically designed for DCM4CHEE and includes all necessary schemas and initial configuration.
