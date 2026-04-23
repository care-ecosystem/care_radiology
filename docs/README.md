# Care Radiology Plugin - Technical Documentation

## Overview

This directory contains comprehensive technical documentation for the care_radiology plugin, covering all aspects of the system architecture, API endpoints, external service integrations, and data flows.

---

## Documentation Index

### 1. [ARCHITECTURE.md](../ARCHITECTURE.md)
**High-level system architecture and overview**
- Project structure and technology stack
- Database models and relationships
- Complete API endpoint reference
- Service integration overview
- Configuration and deployment guides
- Security considerations

**Target Audience**: Developers, DevOps, Technical Architects

---

### 2. [API_UPLOAD_ENDPOINT.md](./API_UPLOAD_ENDPOINT.md)
**Detailed DICOM upload API documentation**
- Complete data flow with diagrams
- Block-by-block code analysis
- Multipart encoding details
- DCM4CHEE STOW-RS integration
- Authorization and authentication
- Performance metrics and optimization
- Error handling and troubleshooting
- Testing guide

**Target Audience**: Backend Developers, API Integrators

**Key Sections**:
- Request/Response specification
- Authorization flow (JWT + permissions)
- DICOM file encoding (multipart/related)
- DCM4CHEE upload workflow
- Study UID extraction logic
- Database record creation
- Cache invalidation strategy

---

### 3. [API_QUERY_ENDPOINT.md](./API_QUERY_ENDPOINT.md)
**Detailed DICOM query API documentation**
- Complete query flow with diagrams
- Parallel metadata fetching with ThreadPoolExecutor
- Redis caching strategy
- DICOM tag parsing (d_find, d_datetime_to_iso)
- QIDO-RS integration details
- Performance optimization strategies
- Cache hit/miss scenarios
- Error handling and graceful degradation

**Target Audience**: Backend Developers, Performance Engineers

**Key Sections**:
- Patient authorization (can_view_patient_obj)
- DicomStudy database queries
- Concurrent DCM4CHEE requests
- Cache key structure and TTL
- DICOM JSON parsing
- Series and instance metadata extraction

---

### 4. [DCM4CHEE_INTEGRATION.md](./DCM4CHEE_INTEGRATION.md)
**Complete DCM4CHEE PACS integration guide**
- DCM4CHEE architecture and components
- PostgreSQL database schema (study, series, instance tables)
- LDAP configuration for storage
- DICOMweb API reference (STOW-RS, QIDO-RS, WADO-RS)
- Management UI features
- MinIO storage integration
- Performance tuning (JVM, PostgreSQL, indexes)
- Monitoring with Prometheus
- Troubleshooting common issues

**Target Audience**: DevOps, System Administrators, PACS Engineers

**Key Sections**:
- Docker configuration
- Database schema and indexes
- LDAP directory structure
- DICOMweb endpoint details
- Storage workflow with MinIO
- Query optimization
- Security and compliance (HIPAA)

---

### 5. [API_SPECIFICATION.md](./API_SPECIFICATION.md)
**Complete API specification and database schema reference**
- Full database schema with all 9 models
- Entity relationship diagrams (ERD)
- Complete API endpoint reference (26 endpoints)
- Request/response schemas (Pydantic specs)
- Authentication & authorization rules
- Performance benchmarks and optimization
- SQL query examples
- API client examples (Python, cURL)

**Target Audience**: Backend Developers, API Integrators, Database Administrators

**Key Sections**:
- Database schema with field-level documentation
- Entity relationship diagrams (ASCII art)
- DICOM operations (upload, query, worklist)
- Study report CRUD with audit trail
- Configuration management (modality, body part, scan protocol, template)
- JWT & static API key authentication
- Permission checks (can_read/write_radiology_report)
- Redis caching strategy
- ThreadPoolExecutor parallel queries
- SQL query examples

---

### 6. [EXTERNAL_SERVICES.md](./EXTERNAL_SERVICES.md)
**Comprehensive guide to all external services**

#### OHIF Viewer
- Configuration (app-config.js)
- DICOMweb endpoint setup
- URL patterns for opening studies
- React integration examples
- Image loading flow
- Performance optimization (prefetching, web workers)
- Troubleshooting (CORS, authentication)

#### MinIO Object Storage
- Installation and configuration
- Bucket creation and policies
- S3 API operations (PUT, GET, HEAD, LIST)
- Object key structure
- Production setup (distributed mode, lifecycle)
- Encryption at rest
- Monitoring metrics

#### OpenLDAP Directory
- LDAP schema for DCM4CHEE
- Storage descriptor configuration
- LDAP operations (search, modify, add, delete)
- Integration with DCM4CHEE
- Troubleshooting LDAP issues

#### Nginx Reverse Proxy
- Complete nginx.conf breakdown
- Routing logic (OHIF, DCM4CHEE, Care)
- Authentication flow (auth_request)
- CORS handling
- Production configuration (SSL, rate limiting)
- Monitoring and logging

**Target Audience**: DevOps, Full-Stack Developers, System Integrators

---

## Documentation Structure

```
docs/
├── README.md                      (This file - Documentation index)
├── API_SPECIFICATION.md           (Complete API spec & database schema)
├── API_UPLOAD_ENDPOINT.md         (Upload API deep dive)
├── API_QUERY_ENDPOINT.md          (Query API deep dive)
├── DCM4CHEE_INTEGRATION.md        (PACS integration guide)
├── EXTERNAL_SERVICES.md           (OHIF, MinIO, LDAP, Nginx)
└── FHIR_ANALYSIS.md               (FHIR R4 compliance analysis)

../ARCHITECTURE.md                  (High-level architecture overview)
```

---

## Quick Links

### Getting Started
- [Local Development Setup](../ARCHITECTURE.md#deployment-guide)
- [Docker Configuration](./DCM4CHEE_INTEGRATION.md#docker-configuration)
- [LDAP Setup](./EXTERNAL_SERVICES.md#openldap-directory)

### API Reference
- [Complete API Specification](./API_SPECIFICATION.md)
- [Database Schema & ERD](./API_SPECIFICATION.md#database-schema)
- [Upload DICOM](./API_UPLOAD_ENDPOINT.md#request-specification)
- [Query Studies](./API_QUERY_ENDPOINT.md#request-specification)
- [Study Reports CRUD](./API_SPECIFICATION.md#study-reports)
- [Configuration Management](./API_SPECIFICATION.md#configuration-management)
- [Webhook Integration](../ARCHITECTURE.md#webhook-handling)

### Troubleshooting
- [Upload Issues](./API_UPLOAD_ENDPOINT.md#troubleshooting)
- [Query Performance](./API_QUERY_ENDPOINT.md#performance-optimization)
- [DCM4CHEE Errors](./DCM4CHEE_INTEGRATION.md#troubleshooting)
- [Nginx 502/401 Errors](./EXTERNAL_SERVICES.md#troubleshooting-3)

### Configuration
- [Environment Variables](../ARCHITECTURE.md#configuration)
- [OHIF app-config.js](./EXTERNAL_SERVICES.md#configuration)
- [MinIO Buckets](./EXTERNAL_SERVICES.md#configuration-for-dcm4chee)
- [Nginx Proxy](./EXTERNAL_SERVICES.md#configuration-file)

---

## Documentation Conventions

### Code Blocks

**Shell Commands**:
```bash
docker compose up -d
```

**Python Code**:
```python
DicomStudy.objects.create(patient=patient, dicom_study_uid=study_uid)
```

**SQL Queries**:
```sql
SELECT * FROM radiology_dicomstudy WHERE patient_id = 123;
```

**HTTP Requests**:
```http
GET /api/care_radiology/dicom/studies/?patientId=<uuid> HTTP/1.1
Authorization: Bearer <JWT>
```

### Diagrams

**Data Flow**:
```
Browser → Nginx → DCM4CHEE → MinIO
```

**Decision Trees**:
```
if cache hit:
    return cached data
else:
    query DCM4CHEE
    cache result
    return data
```

### Call-outs

**Important Information**:
> ⚠️ **IMPORTANT**: Always use `host.docker.internal` for local PostgreSQL

**Notes**:
> 💡 **Note**: Cache TTL is 1 hour (3600 seconds)

**Security Warnings**:
> 🔒 **Security**: Never commit AWS credentials to git

---

## Contributing to Documentation

### Adding New Documentation

1. Create new `.md` file in `docs/` directory
2. Follow existing structure and conventions
3. Add entry to this README
4. Update related documents with cross-references

### Documentation Standards

**File Naming**:
- Use UPPER_SNAKE_CASE for main documents
- Be descriptive: `API_UPLOAD_ENDPOINT.md` not `upload.md`

**Sections**:
- Start with ## for main sections
- Use ### for subsections
- Use #### for detailed subsections

**Code Examples**:
- Include comments explaining complex logic
- Show both request and response
- Provide context (e.g., "This query returns...")

**Cross-References**:
- Link to related documents: `[See DCM4CHEE Integration](./DCM4CHEE_INTEGRATION.md)`
- Link to specific sections: `[Upload Flow](./API_UPLOAD_ENDPOINT.md#data-flow-diagram)`

---

## Document Version History

| Document | Version | Last Updated | Major Changes |
|----------|---------|--------------|---------------|
| ARCHITECTURE.md | 2.0 | 2026-04-22 | Added reporting system, worklist, updated models |
| API_SPECIFICATION.md | 1.0 | 2026-04-23 | **NEW**: Complete API spec with database schema, ERD, 26 endpoints |
| API_UPLOAD_ENDPOINT.md | 1.0 | 2025-04-16 | Complete upload API documentation |
| API_QUERY_ENDPOINT.md | 1.0 | 2025-04-16 | Complete query API documentation |
| DCM4CHEE_INTEGRATION.md | 1.0 | 2025-04-16 | Complete DCM4CHEE integration guide |
| EXTERNAL_SERVICES.md | 1.0 | 2025-04-16 | Complete external services guide |
| FHIR_ANALYSIS.md | 1.0 | 2026-04-22 | **NEW**: FHIR R4 compliance analysis and roadmap |

---

## Feedback and Questions

For questions or suggestions about this documentation:

1. **GitHub Issues**: https://github.com/10bedicu/care_radiology/issues
2. **Care Community**: https://care.ohc.network/
3. **Email**: care-dev@ohc.network

---

## Related Resources

### External Documentation
- [DICOM Standard](https://www.dicomstandard.org/)
- [DICOMweb Specification](https://www.dicomstandard.org/using/dicomweb)
- [DCM4CHEE Wiki](https://github.com/dcm4che/dcm4chee-arc-light/wiki)
- [OHIF Docs](https://docs.ohif.org/)
- [Care Backend Docs](https://care-be-docs.ohc.network/)

### Code Repositories
- [care_radiology](https://github.com/10bedicu/care_radiology)
- [care](https://github.com/ohcnetwork/care)
- [dcm4chee-arc-light](https://github.com/dcm4che/dcm4chee-arc-light)
- [OHIF Viewer](https://github.com/OHIF/Viewers)

---

*Documentation Index Version: 2.0*
*Last Updated: 2026-04-23*
*Maintained by: Care Development Team*
