# Care Radiology Plugin - Kubernetes Deployment

Complete deployment manifests for the Care Radiology Plugin on K3s, integrated with the existing Care infrastructure.

## Architecture

The radiology plugin reuses existing Care infrastructure:

```
Care Namespace
├── Existing Infrastructure (Reused)
│   ├── PostgreSQL (postgres-care-rw) → dicom database
│   ├── Redis (redis)
│   ├── MinIO (minio) → dicom-bucket
│   └── Care Backend (care-backend)
│
└── Radiology Components (New)
    ├── LDAP (dcm4che/slapd-dcm4chee:2.6.8-34.1)
    ├── DCM4CHEE PACS (dcm4che/dcm4chee-arc-psql:5.34.1)
    ├── OHIF Viewer (ohif/app:v3.9.2)
    └── Nginx Proxy (nginx:alpine)
```

## Prerequisites

1. **Care deployment** running in `care` namespace
2. **care-secrets** must exist with:
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`
   - `BUCKET_KEY`
   - `BUCKET_SECRET`
3. **Storage class**: `local-path` (K3s default)
4. **Ingress controller**: nginx-ingress
5. **Access** to postgres-care-1 pod for database initialization

## Quick Start

### Option 1: Automated Deployment (Recommended)

```bash
cd k3s/care/k8s/radiology
chmod +x deploy.sh
./deploy.sh
```

The script will:
- ✓ Deploy all components in correct order
- ✓ Initialize MinIO bucket
- ✓ Initialize DICOM database schema
- ✓ Configure LDAP with MinIO storage
- ✓ Verify deployment

### Option 2: Manual Deployment

#### Step 1: Deploy Secrets and Configuration

```bash
# Create radiology-specific secrets
kubectl apply -f 01-secrets.yaml
kubectl apply -f 02-configmap.yaml
```

#### Step 2: Deploy Infrastructure

```bash
# Create storage
kubectl apply -f 03-pvc.yaml

# Initialize MinIO bucket
kubectl apply -f 00-init-dicom-bucket.yaml
kubectl wait --for=condition=complete job/radiology-init-minio -n care --timeout=120s

# Deploy LDAP (pre-configured with DCM4CHEE defaults)
kubectl apply -f 04-ldap.yaml
kubectl wait --for=condition=ready pod -l component=ldap -n care --timeout=120s
```

#### Step 3: Initialize Database

```bash
# Initialize DICOM database schema
kubectl apply -f 11-init-db-schema.yaml
kubectl wait --for=condition=complete job/radiology-init-db-schema -n care --timeout=180s

# Grant permissions to care user
kubectl exec postgres-care-1 -n care -- \
  psql -U postgres -d dicom -c \
  "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO care; \
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO care; \
   GRANT ALL PRIVILEGES ON SCHEMA public TO care;"
```

#### Step 4: Deploy DCM4CHEE

```bash
# Deploy PACS server
kubectl apply -f 05-dcm4chee.yaml

# Wait for deployment (takes 2-3 minutes)
kubectl wait --for=condition=ready pod -l component=dcm4chee -n care --timeout=300s

# Verify deployment succeeded
kubectl exec deployment/radiology-dcm4chee -n care -- \
  ls -la /opt/wildfly/standalone/deployments/ | grep deployed
```

#### Step 5: Configure MinIO Storage in LDAP

```bash
# Get MinIO credentials
MINIO_KEY=$(kubectl get secret care-secrets -n care -o jsonpath='{.data.BUCKET_KEY}' | base64 -d)
MINIO_SECRET=$(kubectl get secret care-secrets -n care -o jsonpath='{.data.BUCKET_SECRET}' | base64 -d)

# Create LDIF configuration
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

# Copy to LDAP pod
LDAP_POD=$(kubectl get pod -n care -l component=ldap -o jsonpath='{.items[0].metadata.name}')
kubectl cp /tmp/bucketconfig.ldif care/$LDAP_POD:/tmp/bucketconfig.ldif

# Apply configuration
kubectl exec deployment/radiology-ldap -n care -- \
  ldapmodify -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w secret -f /tmp/bucketconfig.ldif
```

#### Step 6: Deploy Viewers and Ingress

```bash
# Deploy OHIF viewer
kubectl apply -f 06-ohif.yaml
kubectl wait --for=condition=ready pod -l component=ohif -n care --timeout=120s

# Deploy Nginx proxy
kubectl apply -f 07-nginx.yaml
kubectl wait --for=condition=ready pod -l component=nginx -n care --timeout=120s

# Deploy ingress
kubectl apply -f 08-ingress.yaml
```

## File Reference

| File | Description | Purpose |
|------|-------------|---------|
| `00-init-dicom-bucket.yaml` | MinIO bucket initialization job | Creates `dicom-bucket` with versioning |
| `01-secrets.yaml` | Radiology-specific secrets | LDAP and WildFly credentials |
| `02-configmap.yaml` | Configuration for all components | Domain, database, storage settings |
| `03-pvc.yaml` | Persistent volume claims | Storage for LDAP and DCM4CHEE |
| `04-ldap.yaml` | LDAP deployment | Pre-configured dcm4che LDAP image |
| `05-dcm4chee.yaml` | DCM4CHEE PACS deployment | DICOM archive server |
| `06-ohif.yaml` | OHIF viewer deployment | Web-based DICOM viewer |
| `07-nginx.yaml` | Nginx proxy deployment | Reverse proxy for routing |
| `08-ingress.yaml` | Ingress resources | External access configuration |
| `11-init-db-schema.yaml` | Database schema initialization | Creates DICOM tables and indexes |
| `deploy.sh` | Automated deployment script | One-command deployment |

## Deployment Sequence (Order Matters!)

**Critical:** Components must be deployed in this exact order:

1. **Secrets & Config** (`01-secrets.yaml`, `02-configmap.yaml`)
2. **Storage** (`03-pvc.yaml`)
3. **MinIO Bucket** (`00-init-dicom-bucket.yaml`)
4. **LDAP** (`04-ldap.yaml`) - Must be ready before DCM4CHEE
5. **Database Schema** (`11-init-db-schema.yaml`) - Must complete before DCM4CHEE
6. **Database Permissions** (via kubectl exec)
7. **DCM4CHEE** (`05-dcm4chee.yaml`) - Wait for deployment to succeed
8. **MinIO LDAP Config** (via kubectl exec)
9. **Viewers** (`06-ohif.yaml`, `07-nginx.yaml`)
10. **Ingress** (`08-ingress.yaml`)

## Configuration

### Domain Configuration

Update in `02-configmap.yaml`:
```yaml
DOMAIN: "radiology.care-k3s.digit.org"
```

Update in `08-ingress.yaml`:
```yaml
spec:
  tls:
  - hosts:
    - radiology.care-k3s.digit.org  # OHIF viewer
    - pacs-admin.care-k3s.digit.org  # DCM4CHEE admin
```

### Storage Class

Update in `03-pvc.yaml` if not using `local-path`:
```yaml
storageClassName: local-path  # Change to your storage class
```

### Resource Limits

Adjust in component manifests if needed:
- LDAP: 512Mi-1Gi memory, 250m-1000m CPU
- DCM4CHEE: 3Gi-8Gi memory, 1000m-4000m CPU
- OHIF: 512Mi-1Gi memory, 250m-1000m CPU

## Verification

### Check Deployment Status

```bash
# All pods should be Running
kubectl get pods -n care -l app=care-radiology

# Expected output:
# radiology-dcm4chee-xxx   1/1   Running
# radiology-ldap-xxx       1/1   Running
# radiology-nginx-xxx      1/1   Running (2 replicas)
# radiology-ohif-xxx       1/1   Running (2 replicas)
```

### Test DCM4CHEE API

```bash
# Test AE titles endpoint
kubectl exec deployment/radiology-dcm4chee -n care -- \
  curl -s http://localhost:8080/dcm4chee-arc/aets

# Expected: JSON array with DCM4CHEE and other AE titles
```

### Test DICOM Endpoint

```bash
# Test QIDO-RS studies endpoint
kubectl exec deployment/radiology-dcm4chee -n care -- \
  curl -s http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies

# Expected: Empty array [] (no studies yet) or list of studies
```

### Check Database

```bash
# Verify DICOM tables exist
kubectl exec postgres-care-1 -n care -- \
  psql -U postgres -d dicom -c "\dt" | grep study

# Expected: study, series, instance tables
```

### Check MinIO Bucket

```bash
# Port-forward MinIO
kubectl port-forward -n care svc/minio 9000:9000

# Access MinIO Console: http://localhost:9000
# Look for dicom-bucket
```

## Access URLs

After DNS configuration:

- **OHIF Viewer**: https://radiology.care-k3s.digit.org
- **DCM4CHEE Admin**: https://pacs-admin.care-k3s.digit.org
- **DICOMweb API**: https://radiology.care-k3s.digit.org/dicomweb

### Credentials

- **LDAP Admin**: `cn=admin,dc=dcm4che,dc=org` / `secret`
- **WildFly Admin**: `admin` / `admin`
- **MinIO**: (from care-secrets)

## Testing

### Using Postman Collection

```bash
# Import the collection
k8s/radiology/Care-Radiology-Tests.postman_collection.json

# Port-forward for local testing
kubectl port-forward -n care svc/radiology-nginx 8080:80

# Test endpoints at http://localhost:8080
```

### Upload Test DICOM File

```bash
# Using curl (requires DICOM file)
curl -X POST \
  -H "Content-Type: multipart/related; type=application/dicom" \
  --data-binary @test.dcm \
  http://localhost:8080/dicomweb/dcm4chee-arc/aets/DCM4CHEE/rs/studies
```

## Troubleshooting

### DCM4CHEE Deployment Failed

```bash
# Check deployment status
kubectl exec deployment/radiology-dcm4chee -n care -- \
  ls -la /opt/wildfly/standalone/deployments/

# If .failed file exists, check error
kubectl exec deployment/radiology-dcm4chee -n care -- \
  cat /opt/wildfly/standalone/deployments/dcm4chee-arc-ear-5.34.1-psql.ear.failed

# Check logs
kubectl logs -f deployment/radiology-dcm4chee -n care
```

### Common Issues

| Issue | Solution |
|-------|----------|
| LDAP authentication failed | Verify radiology-secrets has correct passwords |
| Database schema not found | Run 11-init-db-schema.yaml job |
| Database permission denied | Grant permissions as shown in Step 3 |
| Device not found in LDAP | Check ARCHIVE_DEVICE_NAME matches (`dcm4chee-arc`) |
| MinIO storage not working | Apply bucketconfig.ldif as shown in Step 5 |
| OHIF viewer blank | Check DICOMweb endpoints in 06-ohif.yaml |

### View Logs

```bash
# DCM4CHEE logs
kubectl logs -f deployment/radiology-dcm4chee -n care

# LDAP logs
kubectl logs -f deployment/radiology-ldap -n care

# OHIF logs
kubectl logs -f deployment/radiology-ohif -n care

# Nginx logs
kubectl logs -f deployment/radiology-nginx -n care
```

## Uninstallation

```bash
# Delete all radiology components
kubectl delete -f 08-ingress.yaml
kubectl delete -f 07-nginx.yaml
kubectl delete -f 06-ohif.yaml
kubectl delete -f 05-dcm4chee.yaml
kubectl delete -f 04-ldap.yaml
kubectl delete -f 03-pvc.yaml
kubectl delete -f 02-configmap.yaml
kubectl delete -f 01-secrets.yaml
kubectl delete job radiology-init-minio radiology-init-db-schema -n care

# Delete DICOM database (optional)
kubectl exec postgres-care-1 -n care -- psql -U postgres -c "DROP DATABASE dicom;"

# Delete MinIO bucket (optional)
kubectl exec deployment/minio -n care -- mc rb myminio/dicom-bucket --force
```

## Production Considerations

1. **Backup Strategy**
   - PostgreSQL DICOM database
   - LDAP configuration
   - MinIO dicom-bucket
   - DCM4CHEE persistent volume

2. **Resource Scaling**
   - Increase DCM4CHEE replicas for HA
   - Adjust memory/CPU based on load
   - Monitor storage growth

3. **Security**
   - Change default LDAP passwords
   - Enable TLS for all endpoints
   - Implement proper RBAC
   - Network policies for pod-to-pod communication

4. **Monitoring**
   - DCM4CHEE metrics endpoint
   - Database connection pool
   - Storage usage
   - DICOM upload success/failure rates

## References

- [DCM4CHEE Documentation](https://github.com/dcm4che/dcm4chee-arc-light/wiki)
- [OHIF Viewer](https://docs.ohif.org/)
- [DICOMweb Standard](https://www.dicomstandard.org/using/dicomweb)
- [Care Radiology Plugin](https://github.com/10bedicu/care_radiology)
