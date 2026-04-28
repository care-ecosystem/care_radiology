# Care Radiology Plugin - K8s Manifests

This directory contains Kubernetes manifests for deploying the Care Radiology plugin components in the **existing care namespace**, reusing the care infrastructure (PostgreSQL, Redis, MinIO).

## Architecture

The radiology plugin integrates with existing care infrastructure:

```
Care Namespace
├── Existing Infrastructure (Reused)
│   ├── PostgreSQL (postgres-care-rw)
│   ├── Redis (redis)
│   ├── MinIO (minio)
│   └── Care Backend (care-backend)
│
└── Radiology Components (New)
    ├── OpenLDAP (radiology-ldap)
    ├── DCM4CHEE PACS (radiology-dcm4chee)
    ├── OHIF Viewer (radiology-ohif)
    └── Nginx Proxy (radiology-nginx)
```

## What's Reused

### From Care Infrastructure
- **PostgreSQL**: Creates new `dicom` database in existing postgres-care cluster
- **Redis**: Shared redis instance for caching
- **MinIO**: Creates new `dicom-storage` bucket in existing minio
- **Care Backend**: Authentication endpoint for DICOM access

### New Components
- **OpenLDAP**: User authentication for DCM4CHEE
- **DCM4CHEE**: PACS archive server (DICOM storage & processing)
- **OHIF Viewer**: Web-based DICOM viewer
- **Nginx**: Reverse proxy with authentication

## Prerequisites

1. **Care deployment** must be running in `care` namespace
2. Existing services must be accessible:
   - `postgres-care-rw:5432`
   - `redis:6379`
   - `minio:9000`
   - `care-backend:9000`
3. **Storage class** available for PVCs
4. **Ingress controller** (nginx) installed
5. **cert-manager** (optional, for TLS)

## Quick Start

### 1. Update Secrets

Edit `01-secrets.yaml` and change:
- `LDAP_ADMIN_PASSWORD`
- `LDAP_CONFIG_PASSWORD`
- `WILDFLY_ADMIN_PASSWORD`

```bash
vi 01-secrets.yaml
```

### 2. Update Configuration

Edit `02-configmap.yaml` and update:
- `DOMAIN`: Your domain name
- Storage class in `03-pvc.yaml`
- Domain names in all manifests

### 3. Deploy Components

```bash
# From k3s/care/k8s/radiology/ directory

# Apply in order
kubectl apply -f 01-secrets.yaml
kubectl apply -f 02-configmap.yaml
kubectl apply -f 03-pvc.yaml

# Wait for PVCs
kubectl get pvc -n care --watch

# Initialize MinIO bucket
kubectl apply -f 00-init-dicom-bucket.yaml
kubectl wait --for=condition=complete job/radiology-init-minio -n care --timeout=120s

# Deploy LDAP
kubectl apply -f 04-ldap.yaml
kubectl wait --for=condition=ready pod -l component=ldap -n care --timeout=300s

# Deploy DCM4CHEE (takes 5-10 minutes)
kubectl apply -f 05-dcm4chee.yaml
kubectl wait --for=condition=ready pod -l component=dcm4chee -n care --timeout=600s

# Deploy OHIF viewer
kubectl apply -f 06-ohif.yaml
kubectl wait --for=condition=ready pod -l component=ohif -n care --timeout=300s

# Deploy Nginx proxy
kubectl apply -f 07-nginx.yaml
kubectl wait --for=condition=ready pod -l component=nginx -n care --timeout=120s

# Deploy Ingress
kubectl apply -f 08-ingress.yaml
```

## Verification

### Check All Pods

```bash
kubectl get pods -n care -l app=care-radiology

# Expected output:
# NAME                                READY   STATUS    RESTARTS   AGE
# radiology-ldap-xxx                  1/1     Running   0          5m
# radiology-dcm4chee-xxx              1/1     Running   0          4m
# radiology-ohif-xxx                  1/1     Running   0          2m
# radiology-nginx-xxx                 1/1     Running   0          1m
```

### Check Services

```bash
kubectl get svc -n care -l app=care-radiology
```

### Test Endpoints

```bash
# Health check
curl http://radiology.care.example.com/health

# OHIF Viewer
curl -I http://radiology.care.example.com/
```

### Check Infrastructure Integration

```bash
# Check dicom database exists
kubectl exec -n care postgres-care-1 -- psql -U care -l | grep dicom

# Check dicom-storage bucket exists
kubectl exec -n care <minio-pod> -- mc ls myminio/ | grep dicom-storage

# Check DCM4CHEE can connect to PostgreSQL
kubectl logs -n care deployment/radiology-dcm4chee | grep -i "database\|postgres"
```

## Configuration Details

### Database Setup

DCM4CHEE uses a separate `dicom` database in the existing PostgreSQL cluster:

```sql
-- Created by init container in DCM4CHEE deployment
CREATE DATABASE dicom;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### MinIO Bucket

DICOM images are stored in a dedicated bucket:
- Bucket name: `dicom-storage`
- Versioning: Enabled
- Lifecycle: Old versions deleted after 90 days

### Redis Cache

Shares the existing care Redis instance for caching DICOM queries.

## Monitoring

### View Logs

```bash
# DCM4CHEE logs
kubectl logs -f deployment/radiology-dcm4chee -n care

# LDAP logs
kubectl logs -f deployment/radiology-ldap -n care

# Nginx logs
kubectl logs -f deployment/radiology-nginx -n care

# OHIF logs
kubectl logs -f deployment/radiology-ohif -n care
```

### Check Resource Usage

```bash
kubectl top pods -n care -l app=care-radiology
```

## Maintenance

### Backup DICOM Database

```bash
# Backup dicom database
POD=$(kubectl get pod -n care -l app=postgres -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n care $POD -- pg_dump -U care dicom > dicom_backup_$(date +%Y%m%d).sql

# Restore
kubectl exec -i -n care $POD -- psql -U care dicom < dicom_backup_20260427.sql
```

### Backup DICOM Images (MinIO)

```bash
# Port forward MinIO
kubectl port-forward -n care svc/minio 9000:9000

# Use mc to backup
mc alias set careminio http://localhost:9000 $MINIO_USER $MINIO_PASSWORD
mc mirror careminio/dicom-storage ./dicom-backup/
```

### Scale Components

```bash
# Scale DCM4CHEE
kubectl scale deployment radiology-dcm4chee --replicas=2 -n care

# Scale OHIF
kubectl scale deployment radiology-ohif --replicas=3 -n care
```

## Troubleshooting

### DCM4CHEE Won't Start

```bash
# Check if PostgreSQL is accessible
kubectl exec -n care deployment/radiology-dcm4chee -- pg_isready -h postgres-care-rw -p 5432

# Check if LDAP is running
kubectl get pods -n care -l component=ldap

# View DCM4CHEE startup logs
kubectl logs -n care deployment/radiology-dcm4chee --tail=100
```

### DICOM Images Not Storing

```bash
# Check MinIO is accessible
kubectl exec -n care deployment/radiology-dcm4chee -- curl -I http://minio:9000

# Check dicom-storage bucket exists
kubectl exec -n care <minio-pod> -- mc ls myminio/dicom-storage

# Check DCM4CHEE MinIO credentials
kubectl get secret care-secrets -n care -o jsonpath='{.data.BUCKET_KEY}' | base64 -d
```

### Authentication Fails

```bash
# Check Care backend is running
kubectl get pods -n care -l app=care,component=backend

# Test authentication endpoint
kubectl exec -n care deployment/care-backend -- curl -I http://localhost:9000/api/care_radiology/v1/dicom/authenticate/

# Check nginx can reach care-backend
kubectl exec -n care deployment/radiology-nginx -- curl -I http://care-backend:9000
```

## Uninstall

```bash
# Delete radiology components only (keeps care infrastructure)
kubectl delete -f 08-ingress.yaml
kubectl delete -f 07-nginx.yaml
kubectl delete -f 06-ohif.yaml
kubectl delete -f 05-dcm4chee.yaml
kubectl delete -f 04-ldap.yaml
kubectl delete -f 03-pvc.yaml
kubectl delete -f 02-configmap.yaml
kubectl delete -f 01-secrets.yaml
kubectl delete job radiology-init-minio -n care

# Optionally delete DICOM data
kubectl exec -n care postgres-care-1 -- psql -U care -c "DROP DATABASE dicom;"
kubectl exec -n care <minio-pod> -- mc rb --force myminio/dicom-storage
```

## Integration Points

### With Care Backend

1. **Authentication**: `http://care-backend:9000/api/care_radiology/v1/dicom/authenticate/`
2. **Authorization**: Care manages user permissions for DICOM access
3. **Audit Logging**: All DICOM operations logged in Care

### With Care Database

- DICOM metadata stored in separate `dicom` database
- Uses same PostgreSQL cluster as care
- No schema conflicts

### With Care Storage

- DICOM images in dedicated `dicom-storage` bucket
- Separate from care's patient/facility buckets
- Shared MinIO credentials

## File Manifest

```
k3s/care/k8s/radiology/
├── 00-init-dicom-bucket.yaml    # Job to create MinIO bucket
├── 01-secrets.yaml               # Radiology-specific secrets
├── 02-configmap.yaml             # Points to care infrastructure
├── 03-pvc.yaml                   # Only LDAP and DCM4CHEE storage
├── 04-ldap.yaml                  # OpenLDAP deployment
├── 05-dcm4chee.yaml              # PACS archive (uses care infra)
├── 06-ohif.yaml                  # DICOM viewer
├── 07-nginx.yaml                 # Reverse proxy
├── 08-ingress.yaml               # Ingress rules
└── README.md                     # This file
```

## Support

For issues:
1. Check pod logs: `kubectl logs -f <pod-name> -n care`
2. Check events: `kubectl get events -n care --sort-by='.lastTimestamp'`
3. Verify care infrastructure is running
4. Check resource constraints: `kubectl top pods -n care`

---

**Namespace**: care
**Reuses**: PostgreSQL, Redis, MinIO, Care Backend
**New Components**: LDAP, DCM4CHEE, OHIF, Nginx
**Last Updated**: 2026-04-27




Radiology Plugin Deployment Complete

  All radiology plugin components have been successfully deployed to the care namespace! Here's the summary:

  Successfully Deployed Resources:

  Configuration:
  - ✅ radiology-secrets - LDAP, Wildfly admin credentials
  - ✅ radiology-config - Configuration pointing to care infrastructure
  - ✅ radiology-ohif-config - OHIF viewer configuration
  - ✅ radiology-nginx-config - Nginx proxy configuration

  Storage:
  - ✅ radiology-ldap-data PVC (Pending - waiting for nodes)
  - ✅ radiology-dcm4chee-data PVC (Pending - waiting for nodes)

  Services:
  - ✅ radiology-ldap - OpenLDAP authentication service
  - ✅ radiology-dcm4chee - PACS archive server (ClusterIP)
  - ✅ radiology-dcm4chee-dicom - DICOM C-STORE service (NodePort 31112)
  - ✅ radiology-nginx - Reverse proxy with authentication
  - ✅ radiology-ohif - DICOM viewer web interface

  Deployments:
  - ✅ radiology-ldap (1 replica)
  - ✅ radiology-dcm4chee (1 replica)
  - ✅ radiology-ohif (2 replicas)
  - ✅ radiology-nginx (2 replicas)

  Jobs:
  - ✅ radiology-init-minio - MinIO bucket initialization

  Current Status:

  All pods are in Pending status waiting for worker nodes to become available. Once nodes are added to the cluster, the components will automatically start in this order:

  1. MinIO bucket initialization job
  2. OpenLDAP
  3. DCM4CHEE (waits for PostgreSQL and LDAP)
  4. OHIF viewer
  5. Nginx proxy

  ⚠️ Note on Ingress:

  The ingress configuration couldn't be applied due to the nginx ingress controller webhook not being available (no nodes). You'll need to apply it manually once nodes are available:

  kubectl apply -f k3s/care/k8s/radiology/08-ingress.yaml

  Next Steps:

  1. Add worker nodes to the unified-dev cluster
  2. Monitor pod startup: kubectl get pods -n care -l app=care-radiology --watch
  3. Check logs once running: kubectl logs -f deployment/radiology-dcm4chee -n care
  4. Apply ingress after nodes are available
