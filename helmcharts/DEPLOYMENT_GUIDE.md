# Care Radiology - Kubernetes Deployment Guide

Complete guide for deploying Care Radiology plugin to Kubernetes using Helm.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Installation Steps](#installation-steps)
4. [Post-Deployment Configuration](#post-deployment-configuration)
5. [Verification](#verification)
6. [Production Hardening](#production-hardening)
7. [Monitoring Setup](#monitoring-setup)
8. [Backup Configuration](#backup-configuration)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Kubernetes Cluster

- Kubernetes v1.20 or higher
- kubectl configured to access the cluster
- Sufficient resources:
  - **Minimum**: 8 CPU cores, 16GB RAM, 150GB storage
  - **Recommended**: 16 CPU cores, 32GB RAM, 500GB storage

### Tools

```bash
# Install Helm 3
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version

# Verify Helm version >= 3.8
```

### Existing Deployments

- **Care backend** must be already deployed in the cluster
- Care backend should be accessible at `care-backend.care.svc.cluster.local:9000`

---

## Pre-Deployment Checklist

### 1. Review Storage Classes

```bash
# List available storage classes
kubectl get storageclass

# Check default storage class
kubectl get storageclass | grep "(default)"
```

Update `global.storageClass` in values.yaml if needed.

### 2. Prepare Secrets

Create a `secrets.yaml` file with all passwords:

```yaml
# secrets.yaml - DO NOT COMMIT TO GIT
postgresql:
  auth:
    password: "your-strong-postgres-password"

redis:
  auth:
    password: "your-strong-redis-password"

minio:
  auth:
    rootUser: "minio-admin-user"
    rootPassword: "your-strong-minio-password"

ldap:
  env:
    LDAP_ADMIN_PASSWORD: "your-strong-ldap-admin-password"
    LDAP_CONFIG_PASSWORD: "your-strong-ldap-config-password"

dcm4chee:
  env:
    POSTGRES_PASSWORD: "your-strong-postgres-password"  # Same as PostgreSQL
    LDAP_ROOTPASS: "your-strong-ldap-admin-password"    # Same as LDAP admin
    LDAP_CONFIGPASS: "your-strong-ldap-config-password" # Same as LDAP config
    WILDFLY_ADMIN_PASSWORD: "your-strong-wildfly-password"
    STORAGE_ACCESS_KEY: "minio-admin-user"              # Same as MinIO user
    STORAGE_SECRET_KEY: "your-strong-minio-password"    # Same as MinIO password
```

**Security**: Store this file securely and never commit to version control.

### 3. Prepare Custom Values

```bash
# Copy production values template
cp helmcharts/care-radiology/values-production.yaml my-values.yaml

# Edit and customize
vim my-values.yaml
```

Update at minimum:
- `global.domain` - Your domain name
- All passwords (or merge with secrets.yaml)
- `global.storageClass` - Your storage class
- Resource limits based on your cluster capacity

### 4. Configure TLS Certificates

**Option 1: cert-manager (Recommended)**

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml

# Create Let's Encrypt issuer
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@care.example.com  # CHANGE THIS
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

**Option 2: Manual TLS Secret**

```bash
# Create TLS secret from certificate files
kubectl create secret tls radiology-tls \
  --cert=/path/to/tls.crt \
  --key=/path/to/tls.key \
  -n care-radiology
```

---

## Installation Steps

### Step 1: Create Namespace

```bash
kubectl create namespace care-radiology

# Optional: Label namespace for monitoring
kubectl label namespace care-radiology monitoring=enabled
```

### Step 2: Add Helm Repositories

```bash
# Add Bitnami repository (for PostgreSQL, Redis, MinIO)
helm repo add bitnami https://charts.bitnami.com/bitnami

# Update repositories
helm repo update
```

### Step 3: Update Chart Dependencies

```bash
cd helmcharts/care-radiology

# Download chart dependencies
helm dependency update

# Verify dependencies
helm dependency list
```

Expected output:
```
NAME            VERSION    REPOSITORY                              STATUS
postgresql      12.x.x     https://charts.bitnami.com/bitnami      ok
redis           17.x.x     https://charts.bitnami.com/bitnami      ok
minio           12.x.x     https://charts.bitnami.com/bitnami      ok
```

### Step 4: Dry Run Installation

```bash
# Validate configuration without installing
helm install care-radiology . \
  --namespace care-radiology \
  --values my-values.yaml \
  --values secrets.yaml \
  --dry-run --debug
```

Review the output for any errors.

### Step 5: Install Chart

```bash
# Install the chart
helm install care-radiology . \
  --namespace care-radiology \
  --values my-values.yaml \
  --values secrets.yaml \
  --timeout 15m
```

### Step 6: Monitor Installation

```bash
# Watch pod status
watch kubectl get pods -n care-radiology

# View detailed status
kubectl get all -n care-radiology
```

**Expected Timeline**:
- OpenLDAP: 1-2 minutes
- PostgreSQL: 2-3 minutes
- Redis: 1-2 minutes
- MinIO: 2-3 minutes
- DCM4CHEE: 5-8 minutes (waits for dependencies)
- OHIF: 1-2 minutes
- Nginx: 1 minute

**Total**: ~10-15 minutes for all pods to be Ready.

---

## Post-Deployment Configuration

### 1. Configure MinIO Bucket Policies

```bash
# Port-forward to MinIO
kubectl port-forward -n care-radiology svc/care-radiology-minio 9001:9001

# Access MinIO Console: http://localhost:9001
# Login with MinIO credentials from values.yaml

# Via mc CLI (alternative)
mc alias set care-radiology https://localhost:9000 <access-key> <secret-key>
mc admin info care-radiology
```

Verify `dicom-storage` bucket exists.

### 2. Initialize DCM4CHEE Configuration

```bash
# Port-forward to DCM4CHEE Management UI
kubectl port-forward -n care-radiology svc/care-radiology-dcm4chee 8081:8080

# Access: http://localhost:8081/dcm4chee-arc/ui2
# Login with Wildfly credentials from values.yaml
```

**Configuration Tasks**:
1. Navigate to **Devices** → **DCM4CHEE**
2. Verify LDAP connection is successful
3. Check **AE Titles** → Verify `DCM4CHEE_PROD` exists
4. Navigate to **Storage** → Verify MinIO storage system is configured

### 3. Test DICOM Upload

```bash
# Get a sample DICOM file
curl -O https://github.com/dcm4che/dcm4chee-arc-light/raw/master/dcm4chee-arc-ui2/src/assets/iocm_test.dcm

# Upload via Care backend API
export CARE_TOKEN="your-jwt-token"
export PATIENT_ID="patient-uuid"

curl -X POST http://localhost:9000/api/care_radiology/dicom/upload/ \
  -H "Authorization: Bearer $CARE_TOKEN" \
  -F "patient_id=$PATIENT_ID" \
  -F "file=@iocm_test.dcm"
```

### 4. Configure Care Backend

Update Care backend settings to point to the radiology stack:

```python
# In Care backend settings.py
PLUGIN_CONFIGS = {
    'care_radiology': {
        'CARE_RADIOLOGY_DCM4CHEE_DICOMWEB_BASEURL': 'http://care-radiology-nginx.care-radiology.svc.cluster.local/dcm4chee-arc',
        'CARE_RADIOLOGY_WEBHOOK_SECRET': 'your-webhook-secret',
    }
}
```

Restart Care backend pods:
```bash
kubectl rollout restart deployment care-backend -n care
```

---

## Verification

### 1. Health Checks

```bash
# Check all pods are running
kubectl get pods -n care-radiology

# All should show STATUS: Running and READY: 1/1 (or 2/2 for init containers)
```

### 2. Service Connectivity

```bash
# Test nginx health endpoint
kubectl run curl --image=curlimages/curl -i --rm -- \
  curl -s http://care-radiology-nginx.care-radiology.svc.cluster.local/health

# Should return: healthy
```

### 3. Database Verification

```bash
# Connect to PostgreSQL
kubectl exec -it -n care-radiology care-radiology-postgresql-0 -- \
  psql -U postgres -d dicom -c "\dt"

# Should show DCM4CHEE tables (study, series, instance, etc.)
```

### 4. Storage Verification

```bash
# Check MinIO
kubectl exec -it -n care-radiology \
  deployment/care-radiology-minio -- \
  mc ls local/dicom-storage

# Should show empty bucket (or existing DICOM objects if uploaded)
```

### 5. OHIF Viewer Access

```bash
# Get Ingress URL
kubectl get ingress -n care-radiology

# Or port-forward for testing
kubectl port-forward -n care-radiology svc/care-radiology-nginx 8080:80

# Access: http://localhost:8080
# Should see OHIF viewer interface
```

---

## Production Hardening

### 1. Enable NetworkPolicies

```bash
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: care-radiology-netpol
  namespace: care-radiology
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  # Allow from nginx ingress controller
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
  # Allow inter-pod communication
  - from:
    - podSelector: {}
  egress:
  # Allow DNS
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: UDP
      port: 53
  # Allow inter-pod communication
  - to:
    - podSelector: {}
  # Allow to Care backend
  - to:
    - namespaceSelector:
        matchLabels:
          name: care
    - podSelector:
        matchLabels:
          app: care-backend
EOF
```

### 2. Configure Pod Security Standards

```bash
kubectl label namespace care-radiology \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted
```

### 3. Enable Resource Quotas

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ResourceQuota
metadata:
  name: care-radiology-quota
  namespace: care-radiology
spec:
  hard:
    requests.cpu: "20"
    requests.memory: 40Gi
    limits.cpu: "40"
    limits.memory: 80Gi
    persistentvolumeclaims: "10"
EOF
```

### 4. Configure PodDisruptionBudgets

```bash
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: dcm4chee-pdb
  namespace: care-radiology
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: care-radiology-dcm4chee
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: ohif-pdb
  namespace: care-radiology
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: care-radiology-ohif
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: nginx-pdb
  namespace: care-radiology
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: care-radiology-nginx
EOF
```

---

## Monitoring Setup

### 1. Install Prometheus Operator (if not already installed)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

### 2. Configure ServiceMonitors

```bash
cat <<EOF | kubectl apply -f -
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: care-radiology-postgresql
  namespace: care-radiology
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: postgresql
  endpoints:
  - port: metrics
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: care-radiology-redis
  namespace: care-radiology
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: redis
  endpoints:
  - port: metrics
EOF
```

### 3. Import Grafana Dashboards

Access Grafana:
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# Access: http://localhost:3000
# Default credentials: admin / prom-operator
```

Import dashboards:
- PostgreSQL: Dashboard ID `9628`
- Redis: Dashboard ID `11835`
- Nginx: Dashboard ID `9614`

---

## Backup Configuration

### 1. PostgreSQL Automated Backups

```bash
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind:CronJob
metadata:
  name: postgresql-backup
  namespace: care-radiology
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:15
            env:
            - name: PGPASSWORD
              value: "your-postgres-password"
            command:
            - /bin/sh
            - -c
            - |
              pg_dump -h care-radiology-postgresql -U postgres dicom | \
              gzip > /backup/dicom-\$(date +%Y%m%d-%H%M%S).sql.gz
            volumeMounts:
            - name: backup
              mountPath: /backup
          restartPolicy: OnFailure
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: postgresql-backup-pvc
EOF
```

### 2. MinIO Replication

Configure MinIO site replication for disaster recovery:

```bash
# On primary site
mc admin replicate add primary https://minio-primary:9000 \
  https://minio-dr:9000 \
  --access-key <key> --secret-key <secret>
```

---

## Troubleshooting

See [helmcharts/README.md#troubleshooting](./README.md#troubleshooting) for common issues and solutions.

### Additional Debug Commands

```bash
# View all events in namespace
kubectl get events -n care-radiology --sort-by='.lastTimestamp'

# Describe failed pod
kubectl describe pod <pod-name> -n care-radiology

# Get pod logs
kubectl logs <pod-name> -n care-radiology --previous

# Execute commands in pod
kubectl exec -it <pod-name> -n care-radiology -- /bin/sh
```

---

## Upgrade Procedure

```bash
# Pull latest chart
git pull origin main

# Update dependencies
cd helmcharts/care-radiology
helm dependency update

# Upgrade release
helm upgrade care-radiology . \
  --namespace care-radiology \
  --values my-values.yaml \
  --values secrets.yaml \
  --timeout 15m

# Verify upgrade
helm list -n care-radiology
kubectl rollout status deployment -n care-radiology
```

---

## Rollback Procedure

```bash
# View release history
helm history care-radiology -n care-radiology

# Rollback to previous revision
helm rollback care-radiology -n care-radiology

# Or rollback to specific revision
helm rollback care-radiology <revision> -n care-radiology
```

---

## Complete Uninstallation

```bash
# Delete Helm release
helm uninstall care-radiology -n care-radiology

# Delete PVCs (WARNING: This deletes all data)
kubectl delete pvc -n care-radiology -l app.kubernetes.io/instance=care-radiology

# Delete namespace
kubectl delete namespace care-radiology
```

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/10bedicu/care_radiology/issues
- Documentation: https://github.com/10bedicu/care_radiology/tree/main/docs
- Community: https://care.ohc.network/
