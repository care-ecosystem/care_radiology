Great — this is a perfect place to document learnings. I’ll structure this as a **practical FAQ for engineers** working with the CARE Radiology Plugin locally 👇

---

# 📘 CARE Radiology Plugin – Local Setup FAQ

---

## 🧠 1. What is the Radiology Plugin in CARE?

It is a **Django plugin** that integrates CARE with a full radiology stack:

* **DCM4CHEE** → DICOM archive (PACS)
* **MinIO** → Image storage
* **OHIF** → Web-based DICOM viewer
* **LDAP + Postgres** → Supporting services

👉 CARE acts as:

* Workflow orchestrator
* Metadata manager
* Not the image storage system

---

## ⚙️ 2. Do I need extra services to run this plugin locally?

👉 **Yes**

This plugin is **infra-dependent**, not just backend logic.

You must run:

* DCM4CHEE
* LDAP
* MinIO
* OHIF

Using:

```bash
docker compose -f docker-compose.radiology.yaml up -d
```

---

## 🔀 3. Can I run radiology stack independently from CARE?

👉 **Yes (recommended)**

### Approach:

* Run CARE separately:

```bash
make up
```

* Run radiology stack independently:

```bash
docker compose -f docker-compose.radiology.yaml up -d
```

👉 Then connect via:

```python
DCM4CHEE_DICOMWEB_BASEURL = http://localhost:<port>/...
```

---

## ❗ 4. Why did I get error: `depends on undefined service backend`?

👉 Because radiology compose assumes CARE services exist.

### Fix:

* Remove:

```yaml
depends_on:
  - backend
```

OR

* Run both compose files together

---

## ⚠️ 5. Why did I get platform mismatch (amd64 vs arm64)?

```bash
linux/amd64 does not match linux/arm64
```

👉 You are on Mac M1/M2 (ARM), images are AMD64.

### Fix:

Add in compose:

```yaml
platform: linux/amd64
```

---

## ❌ 6. Why did OHIF container fail with mount error?

```bash
not a directory / file mismatch
```

👉 Root cause:

* `app-config.js` file missing

### Fix:

```bash
touch docker/ohif/app-config.js
```

Add config and restart.

---

## 📁 7. How should volume mapping look?

Correct:

```yaml
- ./docker/ohif/app-config.js:/usr/share/nginx/html/app-config.js
```

Wrong:

```yaml
- ./docker/ohif:/usr/share/nginx/html/app-config.js
```

---

## 🧪 8. How do I verify everything is working?

### Check containers:

```bash
docker ps
```

### Access:

* OHIF Viewer → `http://localhost:<port>`
* DCM4CHEE UI → `http://localhost:8080/dcm4chee-arc/ui2`

---

## 🗄️ 9. Do I need to setup database manually?

👉 Yes (one-time)

```bash
cd docker/dcm4che
make setup-dicom-db
```

---

## 📦 10. Do I need to configure MinIO?

👉 Yes

* Open MinIO UI
* Create bucket:

```bash
dicom-bucket
```

---

## 🔐 11. Why is LDAP required?

👉 DCM4CHEE uses LDAP for:

* Configuration
* Storage mapping

### Important:

You must import:

```bash
bucketconfig.ldif
```

Otherwise:

* Images won’t be stored properly

---

## 🌐 12. Why is OHIF not showing images?

Common reasons:

* ❌ Wrong DICOMweb URL
* ❌ Not publicly accessible
* ❌ Port mismatch

### Fix:

Update:

```js
app-config.js
```

---

## 🔗 13. How does CARE connect to radiology stack?

Via:

```python
DCM4CHEE_DICOMWEB_BASEURL
```

👉 CARE calls DICOMweb APIs:

* QIDO (query)
* WADO (retrieve)

---

## 🧠 14. Does CARE store images?

👉 **No**

CARE only:

* Stores references
* Links studies to patients

Images are stored in:

* MinIO via DCM4CHEE

---

## ⚠️ 15. What are common local setup issues?

| Issue                  | Cause                   | Fix                         |
| ---------------------- | ----------------------- | --------------------------- |
| Container not starting | Missing platform config | Add `platform: linux/amd64` |
| Mount error            | Missing file            | Create `app-config.js`      |
| No images visible      | Wrong URL               | Fix OHIF config             |
| Upload fails           | LDAP/MinIO misconfig    | Import LDIF + create bucket |
| CARE can't connect     | Wrong host              | Use `host.docker.internal`  |

---

## 💡 16. Should I always run radiology stack?

👉 No

### Recommended modes:

| Mode          | Usage          |
| ------------- | -------------- |
| Normal dev    | Skip radiology |
| Radiology dev | Run full stack |

---

## 🚀 17. What are key architectural learnings?

### 🔴 Current State

* Plugin tightly coupled with infra
* Requires Docker + multiple services
* Hard to run independently

### 🟢 Ideal Future

* Radiology as **independent service**
* CARE plugin = only integration layer
* Replace LDAP with simpler config
* Support pluggable DICOM providers

---

## 🧾 18. Final takeaway

👉 The radiology plugin is not just a feature — it is a **full radiology subsystem integrated into CARE**.

Running it locally means:

* Managing a mini distributed system
* Not just a Django plugin

---

If you want, I can next convert this into:

* 📄 **Internal Confluence/Notion doc**
* 🧩 **Architecture diagram (CARE + Radiology + DIGIT integration)**
* ⚙️ **Kubernetes deployment version (production-ready)**
