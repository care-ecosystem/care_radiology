# Care Radiology Helm Charts

Complete Kubernetes deployment for Care Radiology plugin with PACS, DICOM viewer, and all dependencies.

## Overview

This Helm chart deploys a complete radiology imaging stack including:

- **DCM4CHEE PACS Archive** (v5.34.1) - DICOM storage and management
- **OHIF Viewer** (v3.9.2) - Web-based DICOM viewer
- **PostgreSQL** - Database for DCM4CHEE metadata
- **MinIO** - S3-compatible object storage for DICOM files
- **OpenLDAP** - Configuration store for DCM4CHEE
- **Redis** - Caching layer for study metadata
- **Nginx** - Reverse proxy with authentication

## Prerequisites

- Kubernetes 1.20+
- Helm 3.8+
- PV provisioner support in the underlying infrastructure (for persistence)
- Care backend already deployed (for authentication)

## Installation

### Quick Start

```bash
# Add Bitnami repository (for PostgreSQL, Redis, MinIO)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install the chart
helm install care-radiology ./care-radiology \
  --namespace care-radiology \
  --create-namespace

# Wait for all pods to be ready
kubectl wait --for=condition=ready pod --all -n care-radiology --timeout=600s
```

### Production Installation

1. **Create a custom values file**:

```bash
cp care-radiology/values-production.yaml my-values.yaml
```

2. **Edit `my-values.yaml`** and change:
   - All passwords (PostgreSQL, MinIO, LDAP, DCM4CHEE)
   - Domain names
   - Storage class
   - Resource limits
   - Ingress configuration

3. **Install with custom values**:

```bash
helm install care-radiology ./care-radiology \
  --namespace care-radiology \
  --create-namespace \
  --values my-values.yaml
```

## Configuration

### Key Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.domain` | Base domain for the deployment | `care.local` |
| `global.storageClass` | Storage class for PVCs | `standard` |
| `postgresql.enabled` | Enable PostgreSQL | `true` |
| `postgresql.auth.password` | PostgreSQL password | `postgres` |
| `postgresql.primary.persistence.size` | PostgreSQL PVC size | `20Gi` |
| `redis.enabled` | Enable Redis cache | `true` |
| `minio.enabled` | Enable MinIO storage | `true` |
| `minio.auth.rootUser` | MinIO admin username | `minioadmin` |
| `minio.auth.rootPassword` | MinIO admin password | `minioadmin` |
| `minio.persistence.size` | MinIO PVC size | `100Gi` |
| `dcm4chee.enabled` | Enable DCM4CHEE PACS | `true` |
| `dcm4chee.env.WILDFLY_ADMIN_PASSWORD` | DCM4CHEE admin password | `admin` |
| `ohif.enabled` | Enable OHIF viewer | `true` |
| `nginx.enabled` | Enable Nginx proxy | `true` |
| `ingress.enabled` | Enable Ingress | `false` |
| `ingress.className` | Ingress class name | `nginx` |

### Complete Values Documentation

See [care-radiology/values.yaml](./care-radiology/values.yaml) for all available parameters with descriptions.

## Accessing Services

### After Installation

The chart will display access instructions in the NOTES output. To view again:

```bash
helm status care-radiology -n care-radiology
```

### OHIF Viewer

**Port-forward method**:
```bash
kubectl port-forward svc/care-radiology-nginx -n care-radiology 8080:80
# Access at: http://localhost:8080
```

**Ingress method** (if enabled):
```bash
# Access at your configured domain
# Example: https://radiology.care.example.com
```

### DCM4CHEE Management UI

```bash
kubectl port-forward svc/care-radiology-dcm4chee -n care-radiology 8081:8080
# Access at: http://localhost:8081/dcm4chee-arc/ui2
# Default credentials: admin / admin
```

### MinIO Console

```bash
kubectl port-forward svc/care-radiology-minio -n care-radiology 9001:9001
# Access at: http://localhost:9001
# Default credentials: minioadmin / minioadmin
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Ingress                            │
│                    (Optional, with TLS)                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   Nginx Proxy        │
              │  (Authentication)    │
              └──┬─────────────┬─────┘
                 │             │
         ┌───────▼──────┐     │
         │  OHIF Viewer │     │
         │  (Frontend)  │     │
         └──────────────┘     │
                              │
                     ┌────────▼──────────┐
                     │   DCM4CHEE PACS   │
                     │  (DICOM Server)   │
                     └─┬────────┬────────┘
                       │        │
              ┌────────▼──┐  ┌─▼──────────┐
              │PostgreSQL │  │   MinIO    │
              │(Metadata) │  │ (Storage)  │
              └───────────┘  └────────────┘
                       │
                  ┌────▼─────┐
                  │ OpenLDAP │
                  │ (Config) │
                  └──────────┘

         ┌──────────────┐
         │    Redis     │
         │   (Cache)    │
         └──────────────┘
```

## Persistence

By default, persistent volumes are created for:

- PostgreSQL: 20Gi (database)
- MinIO: 100Gi (DICOM files)
- DCM4CHEE: 5Gi (logs, temp storage)
- OpenLDAP: 1Gi (configuration)
- Redis: 2Gi (cache)

**Total minimum storage**: ~128Gi

### Disable Persistence (for testing)

```yaml
postgresql:
  primary:
    persistence:
      enabled: false

minio:
  persistence:
    enabled: false

# ... etc
```

## Upgrading

### Update Chart Dependencies

```bash
cd care-radiology
helm dependency update
```

### Upgrade Release

```bash
helm upgrade care-radiology ./care-radiology \
  --namespace care-radiology \
  --values my-values.yaml
```

### Rollback

```bash
# View release history
helm history care-radiology -n care-radiology

# Rollback to previous version
helm rollback care-radiology -n care-radiology
```

## Uninstalling

```bash
# Uninstall the release
helm uninstall care-radiology -n care-radiology

# Delete PVCs (if you want to delete data)
kubectl delete pvc -n care-radiology -l app.kubernetes.io/instance=care-radiology

# Delete namespace
kubectl delete namespace care-radiology
```

## Troubleshooting

### Check Pod Status

```bash
kubectl get pods -n care-radiology
```

### View Pod Logs

```bash
# DCM4CHEE logs
kubectl logs -f -n care-radiology deployment/care-radiology-dcm4chee

# OHIF logs
kubectl logs -f -n care-radiology deployment/care-radiology-ohif

# Nginx logs
kubectl logs -f -n care-radiology deployment/care-radiology-nginx
```

### Common Issues

#### 1. DCM4CHEE Pod Stuck in Init

**Symptom**: DCM4CHEE pod shows `Init:0/1` status for >5 minutes.

**Cause**: PostgreSQL or LDAP not ready.

**Solution**:
```bash
# Check PostgreSQL
kubectl logs -n care-radiology -l app.kubernetes.io/name=postgresql

# Check LDAP
kubectl logs -n care-radiology -l app.kubernetes.io/component=ldap
```

#### 2. OHIF Cannot Load Studies

**Symptom**: OHIF UI loads but shows "No studies found" or network errors.

**Cause**: Authentication or DICOMweb endpoint misconfigured.

**Solution**:
```bash
# Check nginx configuration
kubectl describe configmap care-radiology-nginx-config -n care-radiology

# Check Care backend connectivity
kubectl exec -it -n care-radiology deployment/care-radiology-nginx -- curl http://care-backend:9000/api/care_radiology/dicom/authenticate/
```

#### 3. Out of Storage

**Symptom**: MinIO or PostgreSQL pods fail with disk pressure errors.

**Solution**:
```bash
# Increase PVC size in values.yaml, then upgrade
helm upgrade care-radiology ./care-radiology \
  --namespace care-radiology \
  --values my-values.yaml \
  --reuse-values \
  --set minio.persistence.size=200Gi
```

#### 4. Memory Issues

**Symptom**: DCM4CHEE pod OOMKilled.

**Solution**:
```yaml
# Increase memory limits in values.yaml
dcm4chee:
  resources:
    limits:
      memory: 6Gi  # Increased from 4Gi
```

## Production Checklist

Before deploying to production:

- [ ] Change all default passwords
- [ ] Configure Ingress with TLS certificates
- [ ] Set appropriate resource limits
- [ ] Configure backup for PostgreSQL
- [ ] Configure backup for MinIO
- [ ] Enable monitoring (Prometheus/Grafana)
- [ ] Configure NetworkPolicies
- [ ] Test disaster recovery procedures
- [ ] Document custom configurations
- [ ] Enable audit logging
- [ ] Configure LDAP/AD integration (if needed)

## Monitoring

### Prometheus Integration

Enable metrics for PostgreSQL and Redis:

```yaml
postgresql:
  metrics:
    enabled: true

redis:
  metrics:
    enabled: true
```

### Custom Metrics

DCM4CHEE exposes Prometheus metrics at:
```
http://dcm4chee:9990/metrics
```

## Backup and Restore

### PostgreSQL Backup

```bash
# Create backup
kubectl exec -n care-radiology -it care-radiology-postgresql-0 -- \
  pg_dump -U postgres dicom > dicom-backup-$(date +%Y%m%d).sql

# Restore backup
kubectl exec -n care-radiology -i care-radiology-postgresql-0 -- \
  psql -U postgres dicom < dicom-backup-20240315.sql
```

### MinIO Backup

Use MinIO's built-in replication or use `mc mirror`:

```bash
# Install mc (MinIO client)
# Copy data to backup location
mc mirror care-radiology/dicom-storage backup-location/dicom-storage
```

## Security

### Network Policies

Apply NetworkPolicy to restrict pod-to-pod communication:

```yaml
# network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: care-radiology-netpol
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/instance: care-radiology
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app.kubernetes.io/instance: care-radiology
  egress:
  - to:
    - podSelector:
        matchLabels:
          app.kubernetes.io/instance: care-radiology
```

### Secret Management

Use Kubernetes Secrets or external secret managers:

```bash
# Create secret for passwords
kubectl create secret generic care-radiology-secrets \
  --from-literal=postgres-password=<strong-password> \
  --from-literal=minio-password=<strong-password> \
  -n care-radiology
```

Then reference in values:

```yaml
postgresql:
  auth:
    existingSecret: care-radiology-secrets
    secretKeys:
      adminPasswordKey: postgres-password
```

## Contributing

Please refer to the main repository for contribution guidelines:
https://github.com/10bedicu/care_radiology

## License

See the main repository for license information.

## Support

- Documentation: https://github.com/10bedicu/care_radiology/tree/main/docs
- Issues: https://github.com/10bedicu/care_radiology/issues
- Community: https://care.ohc.network/
