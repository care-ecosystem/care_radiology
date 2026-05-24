#!/bin/bash
set -e

# Care Radiology Plugin Deployment Script
# This script deploys the complete radiology stack to K3s

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECONFIG="${KUBECONFIG:-/Users/jagankumar/Office/Work/repo/Care/care_deployment/k3s/kubeconfig}"
NAMESPACE="care"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl not found. Please install kubectl first."
        exit 1
    fi

    if [ ! -f "$KUBECONFIG" ]; then
        log_error "Kubeconfig not found at $KUBECONFIG"
        exit 1
    fi

    # Check if namespace exists
    if ! kubectl --kubeconfig="$KUBECONFIG" get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace '$NAMESPACE' does not exist"
        exit 1
    fi

    # Check if care-secrets exists
    if ! kubectl --kubeconfig="$KUBECONFIG" get secret care-secrets -n "$NAMESPACE" &> /dev/null; then
        log_error "Secret 'care-secrets' does not exist in namespace '$NAMESPACE'"
        exit 1
    fi

    log_info "Prerequisites check passed ✓"
}

deploy_secrets() {
    log_info "Deploying radiology secrets..."

    kubectl --kubeconfig="$KUBECONFIG" apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: radiology-secrets
  namespace: $NAMESPACE
  labels:
    app: care-radiology
type: Opaque
stringData:
  LDAP_ADMIN_PASSWORD: "secret"
  LDAP_CONFIG_PASSWORD: "secret"
  WILDFLY_ADMIN_USER: "admin"
  WILDFLY_ADMIN_PASSWORD: "admin"
EOF

    log_info "Secrets deployed ✓"
}

deploy_infrastructure() {
    log_info "Deploying infrastructure components..."

    # Deploy in order
    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/02-configmap.yaml"
    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/03-pvc.yaml"
    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/04-ldap.yaml"

    log_info "Waiting for LDAP to be ready..."
    kubectl --kubeconfig="$KUBECONFIG" wait --for=condition=ready pod -l component=ldap -n "$NAMESPACE" --timeout=120s

    log_info "Infrastructure deployed ✓"
}

initialize_minio_bucket() {
    log_info "Initializing MinIO bucket..."

    kubectl --kubeconfig="$KUBECONFIG" delete job radiology-init-minio -n "$NAMESPACE" 2>/dev/null || true
    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/00-init-dicom-bucket.yaml"

    log_info "Waiting for bucket initialization..."
    kubectl --kubeconfig="$KUBECONFIG" wait --for=condition=complete job/radiology-init-minio -n "$NAMESPACE" --timeout=120s

    log_info "MinIO bucket initialized ✓"
}

initialize_database() {
    log_info "Initializing DICOM database schema..."

    # Create database if it doesn't exist (idempotent)
    kubectl --kubeconfig="$KUBECONFIG" exec postgres-care-1 -n "$NAMESPACE" -- \
        psql -U postgres -c "CREATE DATABASE dicom;" 2>/dev/null || log_warn "Database 'dicom' already exists"

    # Apply schema initialization job
    kubectl --kubeconfig="$KUBECONFIG" delete job radiology-init-db-schema -n "$NAMESPACE" 2>/dev/null || true
    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/11-init-db-schema.yaml"

    log_info "Waiting for database initialization..."
    kubectl --kubeconfig="$KUBECONFIG" wait --for=condition=complete job/radiology-init-db-schema -n "$NAMESPACE" --timeout=180s

    # Grant permissions to care user
    log_info "Granting database permissions..."
    kubectl --kubeconfig="$KUBECONFIG" exec postgres-care-1 -n "$NAMESPACE" -- \
        psql -U postgres -d dicom -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO care; GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO care; GRANT ALL PRIVILEGES ON SCHEMA public TO care;"

    log_info "Database initialized ✓"
}

deploy_dcm4chee() {
    log_info "Deploying DCM4CHEE PACS server..."

    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/05-dcm4chee.yaml"

    log_info "Waiting for DCM4CHEE to be ready (this may take 2-3 minutes)..."
    kubectl --kubeconfig="$KUBECONFIG" wait --for=condition=ready pod -l component=dcm4chee -n "$NAMESPACE" --timeout=300s

    # Wait a bit more for deployment to complete
    sleep 30

    # Check deployment status
    DEPLOYMENT_STATUS=$(kubectl --kubeconfig="$KUBECONFIG" exec deployment/radiology-dcm4chee -n "$NAMESPACE" -- \
        ls -la /opt/wildfly/standalone/deployments/ 2>/dev/null | grep "dcm4chee-arc-ear" | grep "deployed" || echo "")

    if [ -z "$DEPLOYMENT_STATUS" ]; then
        log_error "DCM4CHEE deployment failed. Checking logs..."
        kubectl --kubeconfig="$KUBECONFIG" exec deployment/radiology-dcm4chee -n "$NAMESPACE" -- \
            cat /opt/wildfly/standalone/deployments/dcm4chee-arc-ear-5.34.1-psql.ear.failed 2>/dev/null || true
        exit 1
    fi

    log_info "DCM4CHEE deployed successfully ✓"
}

configure_minio_storage() {
    log_info "Configuring MinIO storage in LDAP..."

    # Get MinIO credentials
    MINIO_KEY=$(kubectl --kubeconfig="$KUBECONFIG" get secret care-secrets -n "$NAMESPACE" -o jsonpath='{.data.BUCKET_KEY}' | base64 -d)
    MINIO_SECRET=$(kubectl --kubeconfig="$KUBECONFIG" get secret care-secrets -n "$NAMESPACE" -o jsonpath='{.data.BUCKET_SECRET}' | base64 -d)

    # Create LDIF file
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
    LDAP_POD=$(kubectl --kubeconfig="$KUBECONFIG" get pod -n "$NAMESPACE" -l component=ldap -o jsonpath='{.items[0].metadata.name}')
    kubectl --kubeconfig="$KUBECONFIG" cp /tmp/bucketconfig.ldif "$NAMESPACE/$LDAP_POD:/tmp/bucketconfig.ldif"

    # Apply configuration
    kubectl --kubeconfig="$KUBECONFIG" exec deployment/radiology-ldap -n "$NAMESPACE" -- \
        ldapmodify -x -H ldap://localhost:389 -D "cn=admin,dc=dcm4che,dc=org" -w secret -f /tmp/bucketconfig.ldif

    rm -f /tmp/bucketconfig.ldif

    log_info "MinIO storage configured ✓"
}

deploy_viewers() {
    log_info "Deploying OHIF viewer and Nginx proxy..."

    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/06-ohif.yaml"
    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/07-nginx.yaml"

    log_info "Waiting for OHIF to be ready..."
    kubectl --kubeconfig="$KUBECONFIG" wait --for=condition=ready pod -l component=ohif -n "$NAMESPACE" --timeout=120s

    log_info "Waiting for Nginx to be ready..."
    kubectl --kubeconfig="$KUBECONFIG" wait --for=condition=ready pod -l component=nginx -n "$NAMESPACE" --timeout=120s

    log_info "Viewers deployed ✓"
}

deploy_ingress() {
    log_info "Deploying ingress resources..."

    kubectl --kubeconfig="$KUBECONFIG" apply -f "$SCRIPT_DIR/08-ingress.yaml"

    log_info "Ingress deployed ✓"
}

verify_deployment() {
    log_info "Verifying deployment..."

    # Check all pods are running
    log_info "Checking pod status..."
    kubectl --kubeconfig="$KUBECONFIG" get pods -n "$NAMESPACE" -l app=care-radiology

    # Test DCM4CHEE API
    log_info "Testing DCM4CHEE API..."
    API_RESPONSE=$(kubectl --kubeconfig="$KUBECONFIG" exec deployment/radiology-dcm4chee -n "$NAMESPACE" -- \
        curl -s http://localhost:8080/dcm4chee-arc/aets 2>/dev/null)

    if echo "$API_RESPONSE" | grep -q "DCM4CHEE"; then
        log_info "DCM4CHEE API is responding ✓"
    else
        log_error "DCM4CHEE API test failed"
        exit 1
    fi

    # Test DICOM endpoint
    log_info "Testing DICOM QIDO-RS endpoint..."
    DICOM_RESPONSE=$(kubectl --kubeconfig="$KUBECONFIG" exec deployment/radiology-dcm4chee -n "$NAMESPACE" -- \
        curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies 2>/dev/null)

    if [ "$DICOM_RESPONSE" = "200" ]; then
        log_info "DICOM endpoint is responding ✓"
    else
        log_warn "DICOM endpoint returned status $DICOM_RESPONSE (may need time to initialize)"
    fi

    log_info "Deployment verification complete ✓"
}

print_summary() {
    echo ""
    echo "================================================"
    echo "  Care Radiology Plugin Deployment Complete!"
    echo "================================================"
    echo ""
    echo "Components deployed:"
    echo "  ✓ LDAP (dcm4che/slapd-dcm4chee:2.6.8-34.1)"
    echo "  ✓ DCM4CHEE PACS (dcm4che/dcm4chee-arc-psql:5.34.1)"
    echo "  ✓ OHIF Viewer (ohif/app:v3.9.2)"
    echo "  ✓ Nginx Proxy"
    echo "  ✓ MinIO bucket: dicom-bucket"
    echo "  ✓ PostgreSQL DICOM database with schema"
    echo ""
    echo "Access URLs (after DNS configuration):"
    echo "  OHIF Viewer: https://radiology.care-k3s.digit.org"
    echo "  DCM4CHEE Admin: https://pacs-admin.care-k3s.digit.org"
    echo "  DICOMweb API: https://radiology.care-k3s.digit.org/dicomweb"
    echo ""
    echo "Next steps:"
    echo "  1. Configure DNS records for the domains above"
    echo "  2. Test DICOM upload using the Postman collection"
    echo "  3. Configure Care backend plugin in plug_config.py"
    echo ""
    echo "To view logs:"
    echo "  kubectl --kubeconfig=$KUBECONFIG logs -f deployment/radiology-dcm4chee -n $NAMESPACE"
    echo ""
    echo "To test the deployment:"
    echo "  kubectl --kubeconfig=$KUBECONFIG exec deployment/radiology-dcm4chee -n $NAMESPACE -- curl http://localhost:8080/dcm4chee-arc/aets"
    echo ""
}

main() {
    log_info "Starting Care Radiology Plugin deployment..."
    echo ""

    check_prerequisites
    deploy_secrets
    deploy_infrastructure
    initialize_minio_bucket
    initialize_database
    deploy_dcm4chee
    configure_minio_storage
    deploy_viewers
    deploy_ingress
    verify_deployment

    print_summary
}

# Run main function
main
