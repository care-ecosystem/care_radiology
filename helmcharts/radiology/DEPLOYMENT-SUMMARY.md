# Care Radiology Plugin - Deployment Summary

**Deployment Date:** 2026-04-28
**Domain:** care-k3s.digit.org
**Cluster:** K3s (3 nodes)

---

## 🌐 Access URLs

### Production URLs (HTTPS)

| Service | URL | Purpose |
|---------|-----|---------|
| **OHIF Viewer** | https://radiology.care-k3s.digit.org | Main DICOM image viewer |
| **PACS Admin** | https://pacs-admin.care-k3s.digit.org | DCM4CHEE administration console |
| **DICOM Web API** | https://radiology.care-k3s.digit.org/dicomweb | DICOMweb REST API endpoints |

### DICOM C-STORE (for modalities)

- **Host:** Any K3s node IP
- **Port:** 31112 (NodePort)
- **AE Title:** DCM4CHEE_PROD

---

## ✅ Deployed Components

All components are running successfully:

```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get pods -n care -l app=care-radiology

NAME                                  READY   STATUS    RESTARTS   AGE
radiology-dcm4chee-686c69fbdb-c5k5t   1/1     Running   0          42m
radiology-ldap-5dd4d58485-d2g5t       1/1     Running   0          12h
radiology-nginx-5cd76bfdb7-sxdkc      1/1     Running   0          28s
radiology-nginx-5cd76bfdb7-w9m2t      1/1     Running   0          36s
radiology-ohif-6b597f5c57-4t8xd       1/1     Running   0          36s
radiology-ohif-6b597f5c57-qq2gd       1/1     Running   0          19s
```

### Component Details

#### 1. DCM4CHEE PACS Server
- **Image:** dcm4che/dcm4chee-arc-psql:5.34.1
- **Replicas:** 1
- **Resources:** 3Gi RAM, 1 CPU (request)
- **Storage:** 20Gi persistent volume
- **Database:** PostgreSQL (dicom database in postgres-care-rw)
- **Object Storage:** MinIO (dicom-storage bucket)

#### 2. OpenLDAP
- **Replicas:** 1
- **Storage:** 2Gi persistent volume
- **Base DN:** dc=radiology,dc=care-k3s,dc=digit,dc=org
- **Admin DN:** cn=admin,dc=radiology,dc=care-k3s,dc=digit,dc=org

#### 3. OHIF Viewer
- **Image:** ohif/app:latest
- **Replicas:** 2
- **Configuration:** Points to https://radiology.care-k3s.digit.org/dicomweb

#### 4. Nginx Proxy
- **Image:** nginx:1.25-alpine
- **Replicas:** 2
- **Purpose:** Routes traffic between OHIF and DCM4CHEE

---

## 🔐 TLS/SSL Configuration

**Cert Manager:** Configured for automatic TLS certificate issuance

**Certificate Issuers:**
- Issuer: `letsencrypt-prod`
- Secrets:
  - `radiology-tls` (for radiology.care-k3s.digit.org)
  - `radiology-dcm4chee-admin-tls` (for pacs-admin.care-k3s.digit.org)

**Note:** Certificates will be automatically provisioned by cert-manager once DNS is configured.

---

## 📊 Infrastructure Integration

### PostgreSQL
- **Service:** postgres-care-rw:5432
- **Database:** dicom (separate from care database)
- **Extensions:** uuid-ossp

### MinIO Object Storage
- **Service:** minio:9000
- **Bucket:** dicom-storage
- **Features:** Versioning enabled, lifecycle policy (90 days)

### Redis Cache
- **Service:** redis:6379
- **Purpose:** Query result caching, session storage

### Care Backend
- **Service:** care-backend:9000
- **Integration:** Authentication endpoint for DICOM access

---

## 🔧 Configuration Files

All configuration files have been updated with production domain:

### Updated Files
- ✅ `02-configmap.yaml` - Domain and LDAP settings
- ✅ `06-ohif.yaml` - OHIF DICOM endpoint URLs
- ✅ `07-nginx.yaml` - Nginx server name
- ✅ `08-ingress.yaml` - Ingress host rules

### Configuration Summary

```yaml
# Domain Configuration
DOMAIN: radiology.care-k3s.digit.org

# LDAP Configuration
LDAP_BASE_DN: dc=radiology,dc=care-k3s,dc=digit,dc=org
LDAP_DOMAIN: radiology.care-k3s.digit.org

# OHIF DICOM Endpoints
wadoUriRoot: https://radiology.care-k3s.digit.org/dicomweb
qidoRoot: https://radiology.care-k3s.digit.org/dicomweb
wadoRoot: https://radiology.care-k3s.digit.org/dicomweb

# Ingress Hosts
- radiology.care-k3s.digit.org
- pacs-admin.care-k3s.digit.org
```

---

## 🌍 DNS Configuration Required

To make the radiology plugin accessible, add these DNS records:

### A Records or CNAME

```dns
radiology.care-k3s.digit.org     → [K3s Cluster IP or Load Balancer]
pacs-admin.care-k3s.digit.org    → [K3s Cluster IP or Load Balancer]
```

**Get your cluster ingress IP:**

```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get svc -n kube-system traefik
```

Or if using nginx ingress:

```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get svc -n ingress-nginx ingress-nginx-controller
```

---

## 📝 Testing the Deployment

### 1. Port-Forward Testing (Local)

```bash
# OHIF Viewer
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig port-forward -n care svc/radiology-nginx 8888:80

# Open browser: http://localhost:8888
```

### 2. Production Testing (after DNS setup)

```bash
# Test OHIF Viewer
curl -I https://radiology.care-k3s.digit.org

# Test DICOM Web API
curl -H "Accept: application/dicom+json" \
  https://radiology.care-k3s.digit.org/dicomweb/studies

# Test PACS Admin
curl -I https://pacs-admin.care-k3s.digit.org
```

### 3. Use Postman Collection

Import the testing collection:
```
/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/care/k8s/radiology/Care-Radiology-Tests.postman_collection.json
```

Update base URLs in Postman:
- Change `http://localhost:8080` → `https://pacs-admin.care-k3s.digit.org`
- Change `http://localhost:8888` → `https://radiology.care-k3s.digit.org`

---

## 🔍 Monitoring and Logs

### Check Pod Status

```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get pods -n care -l app=care-radiology
```

### View Logs

```bash
# DCM4CHEE logs
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig logs -f deployment/radiology-dcm4chee -n care

# OHIF Viewer logs
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig logs -f deployment/radiology-ohif -n care

# Nginx Proxy logs
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig logs -f deployment/radiology-nginx -n care

# LDAP logs
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig logs -f deployment/radiology-ldap -n care
```

### Check Ingress Status

```bash
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig describe ingress radiology-ingress -n care
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig describe ingress radiology-dcm4chee-admin -n care
```

---

## 🚀 Next Steps

### 1. DNS Configuration
- [ ] Add DNS A/CNAME records for radiology.care-k3s.digit.org
- [ ] Add DNS A/CNAME records for pacs-admin.care-k3s.digit.org

### 2. TLS Certificate Verification
- [ ] Wait for cert-manager to issue certificates
- [ ] Verify certificates: `kubectl get certificate -n care`
- [ ] Check certificate secrets: `kubectl get secret -n care | grep tls`

### 3. Upload Test DICOM Data
- [ ] Access DCM4CHEE UI: https://pacs-admin.care-k3s.digit.org/dcm4chee-arc/ui2
- [ ] Upload sample DICOM files
- [ ] Verify images appear in OHIF viewer

### 4. Configure DICOM Modalities
- [ ] Configure your DICOM devices to send to:
  - Host: [K3s Node IP]
  - Port: 31112
  - AE Title: DCM4CHEE_PROD

### 5. Production Hardening
- [ ] Review and update LDAP admin credentials
- [ ] Configure basic auth for PACS admin (optional)
- [ ] Set up monitoring and alerting
- [ ] Configure backup for PostgreSQL dicom database
- [ ] Configure backup for MinIO dicom-storage bucket

---

## 📞 Support and Troubleshooting

### Common Issues

**Issue: Cannot access radiology.care-k3s.digit.org**
- Check DNS configuration
- Verify ingress controller is running
- Check TLS certificate status

**Issue: OHIF shows "No studies found"**
- No DICOM data uploaded yet
- Upload test data via DCM4CHEE admin UI

**Issue: 502 Bad Gateway**
- Check if all pods are running
- Review nginx proxy logs
- Verify DCM4CHEE is fully started

**Issue: Certificate errors**
- Wait for cert-manager to provision certificates (may take 5-10 minutes)
- Check certificate status: `kubectl get certificate -n care`

### Get Help

```bash
# View all radiology resources
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get all,pvc,ingress,configmap,secret -n care -l app=care-radiology

# Check events
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig get events -n care --sort-by='.lastTimestamp' | grep radiology

# Describe problematic pod
kubectl --kubeconfig=/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig describe pod <pod-name> -n care
```

---

## 📚 Additional Documentation

- **Testing Guide:** `TESTING-GUIDE.md`
- **Deployment README:** `README.md`
- **Postman Collection:** `Care-Radiology-Tests.postman_collection.json`

---

**Deployment Status:** ✅ Complete
**Configuration:** ✅ Updated for care-k3s.digit.org
**All Pods:** ✅ Running
**Ready for:** DNS configuration and production use
