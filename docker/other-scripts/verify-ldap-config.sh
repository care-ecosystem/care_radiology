#!/bin/bash

# Script to verify LDAP bucket configuration
# Usage: ./verify-ldap-config.sh

set -e

LDAP_CONTAINER="${LDAP_CONTAINER:-care_radiology-ldap-1}"

echo "=================================================="
echo "Verifying LDAP Bucket Configuration"
echo "=================================================="

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${LDAP_CONTAINER}$"; then
    echo "Error: LDAP container '$LDAP_CONTAINER' is not running."
    exit 1
fi

echo "Searching for storage configuration..."
echo ""

# Search for the storage entry
docker exec "$LDAP_CONTAINER" ldapsearch -x -LLL \
    -b "dicomDeviceName=dcm4chee-arc,cn=Devices,cn=DICOM Configuration,dc=dcm4che,dc=org" \
    "(dcmStorageID=fs1)" \
    dcmStorageID dcmURI dcmProperty

echo ""
echo "=================================================="
echo "If you see dcmProperty entries with MinIO config,"
echo "the configuration was applied successfully!"
echo "=================================================="
