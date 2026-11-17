# ChainVault Phase 4B.1: Staging Preflight & Cloud Migration Safety Report

**Authoritative Repository:** `D:\parjaayi project\CHAINVAULT`  
**Current Active Backend:** `DATABASE_BACKEND=mongodb` (Strictly Unchanged & Authoritative)  
**Execution Scope:** Staging Preflight, Cloud Tooling Audit, Migration Safety Architecture & Risk Assessment  
**Date:** 2026-10-24

---

## 1. Executive Summary & Objective

Phase 4B.1 resolves the technical and architectural prerequisites for transitioning from local Firestore Emulator testing to Google Cloud Firestore staging.

In accordance with strict project safety rules:
- **No Google Cloud resources were provisioned or billed.**
- **No writes were made to Google Cloud Firestore.**
- **No modifications were made to authoritative MongoDB database `chainvault`.**
- **No credentials or secrets were exposed.**
- **The existing local emulator safety gates were preserved untouched.**

---

## 2. Local Tooling & Configuration Verification

### Tooling Status

| Tool | Presence on PATH | Version / Status | Notes |
| :--- | :---: | :---: | :--- |
| **Node.js** | **YES** | v20+ runtime available | Required for Firebase CLI tools via `npx`. |
| **Firebase CLI (`firebase-tools`)** | **YES (via npx)** | `15.34.1` | Accessible via `npx --yes firebase-tools`. Standalone `firebase` executable not on PATH. |
| **Google Cloud CLI (`gcloud`)** | **NO** | Not installed on PATH | Standalone `gcloud` binary is absent. All staging deployment commands must use Firebase CLI or GCP Web Console. |
| **Java JDK** | **YES** | Microsoft OpenJDK 21.0.12 | Verified runtime for local emulator operations. |
| **Python Virtualenv** | **YES** | Python 3.13.14 (`backend/venv`) | Primary backend and test execution runtime. |

### Authentication & Account Status
- Executed `npx --yes firebase-tools login:list`:
  * Output: `! No authorized accounts, run "firebase login"`
  * Confirmed: Zero active credentials or account sessions currently exist for Firebase CLI on this machine.
- Environment variables:
  * `GOOGLE_APPLICATION_CREDENTIALS`: Unset across Process, User, and System scopes.
  * `FIREBASE_TOKEN`: Unset.

### Configuration Artifacts & Secret Protection Review
- [`firebase.json`](file:///d:/parjaayi%20project/CHAINVAULT/firebase.json): Configured with `"rules": "firestore.rules"`, `"indexes": "firestore.indexes.json"`, and port 8080 emulator settings.
- [`firestore.rules`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.rules): Locked down with `allow read, write: if false;`, blocking all direct client SDK access.
- [`firestore.indexes.json`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.indexes.json): Defines 5 verified composite indexes covering application multi-field queries.
- [`.env.example`](file:///d:/parjaayi%20project/CHAINVAULT/.env.example): Fully documented template for `DATABASE_BACKEND`, `FIREBASE_PROJECT_ID`, `FIRESTORE_DATABASE_ID`, `GOOGLE_APPLICATION_CREDENTIALS`, and `JWT_SECRET`.
- [`.gitignore`](file:///d:/parjaayi%20project/CHAINVAULT/.gitignore): **Hardened during Phase 4B.1.** Added explicit ignore rules to guarantee that staging credentials and keys can never be committed:
  ```gitignore
  # Cloud & Service Account Credentials
  *.pem
  *.key
  *service_account*.json
  *service-account*.json
  *credentials*.json
  secrets/
  backend/secrets/

  # Firebase & Cloud Logs
  firebase-debug.log*
  firestore-debug.log*
  ui-debug.log*
  ```

---

## 3. Cloud Migration Safety Architecture Design

### Analysis of Existing Migration Tool (`scripts/migrate_mongo_to_firestore.py`)
Inspection of [`backend/scripts/migrate_mongo_to_firestore.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py) shows that its destination selection is strictly hardcoded to the local loopback emulator via [`validate_emulator_target()`](file:///d:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L148-L174):
```python
if not emulator_host or host_ip not in ("127.0.0.1", "localhost", "::1"):
    raise RuntimeError("SAFETY VIOLATION: FIRESTORE_EMULATOR_HOST is unset...")
```
**Safety Mandate:** This emulator guard **must not be weakened or removed**, ensuring the emulator script can never accidentally point to the cloud.

### Architectural Design: Dedicated Cloud-Staging Migration Tool (`scripts/migrate_mongo_to_cloud_staging.py`)
To migrate data to real Cloud Firestore without target confusion or risk to production, a separate, explicitly gated tool must be introduced.

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│ migrate_mongo_to_firestore.py   │       │ migrate_mongo_to_cloud_staging  │
│ ─────────────────────────────── │       │ ─────────────────────────────── │
│ • Strictly requires Loopback IP │       │ • Strictly requires SA Keyfile  │
│ • Refuses Cloud/Non-loopback    │       │ • Refuses FIRESTORE_EMULATOR    │
│ • Local Development & Testing   │       │ • Rejects Production Projects   │
└─────────────────────────────────┘       └─────────────────────────────────┘
```

#### Seven Mandatory Cloud Safety Gates:
1. **Target Environment Gate (`--target-environment staging`):**
   Requires an explicit command-line flag `--target-environment staging`. Refuses to start if missing or set to any other value.
2. **Strict Project Allowlist:**
   Accepts only the approved non-production staging project ID: `chainvault-staging`.
3. **Prohibited Project Substrings:**
   Regex gate rejecting any project ID containing `prod`, `production`, `live`, `main`, `master`, `real`, or matching `chainvault-prod`.
4. **Target Confusion Guard:**
   Asserts that `FIRESTORE_EMULATOR_HOST` is **completely unset** in the process environment. If set, execution aborts with `TargetConfusionError` to prevent cross-wiring emulator and cloud traffic.
5. **IAM Service Account Authentication:**
   Requires `GOOGLE_APPLICATION_CREDENTIALS` pointing to a valid, git-ignored service account key possessing `roles/datastore.user`. Bypasses are prohibited.
6. **Conflict Detection & Overwrite Prevention:**
   For every record, queries the destination Cloud Firestore document:
   - If document exists and content matches bit-for-bit: records `already_present` and skips write.
   - If document exists and content differs: records `conflict_detected` and halts migration or skips the document.
   - **Never silently overwrites conflicting data.**
7. **Read-Only Source Enforcement:**
   Connects to MongoDB using read-only Motor cursor methods (`.find()`, `count_documents({})`). Possesses zero write, update, delete, or drop calls against MongoDB.

---

## 4. Security & Functional Risk Review

### 1. In-Memory `DEMO_USERS` Authentication
- **Risk:** New users or password changes made through the API do not persist to MongoDB or Firestore.
- **Analysis:** Authentication currently relies on hardcoded bcrypt hashes in `backend/app/routes/auth.py`.
- **Staging Decision:** Keep `DEMO_USERS` in-memory during staging validation. This isolates the database staging tests strictly to evidentiary metadata (`cases`, `evidence`, `audit_logs`, `custody`, `reports`, `checkpoints`) and maintains full compliance with the directive: *"Do not replace the current authentication system with Firebase Authentication."*

### 2. Custody Concurrency & Transaction Retries
- **Risk:** Cloud Firestore transactions take 15–50ms over HTTPS/gRPC compared to <1ms in the local emulator. High concurrency on a single evidence item (`EV-PH4-001`) could cause transaction retry contention.
- **Analysis:** [`acquire_custody_transfer_lock()`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py#L560-L627) uses native `@async_transactional` methods with atomic read-before-write checks and backoff retries.
- **Safeguard:** Lease duration is set to `30.0` seconds with renewal support (`renew_custody_transfer_lock`), providing a substantial margin over network latency. The retry timeout `wait_timeout` should be increased from `0.4s` to `1.5s` when running against cloud endpoints.

### 3. Real Cloud Composite Index Enforcement
- **Risk:** Real Cloud Firestore strictly rejects unindexed multi-field queries with HTTP 400 (`FAILED_PRECONDITION`), unlike the emulator which logs warnings.
- **Analysis:** All 5 required composite queries are documented and defined in [`firestore.indexes.json`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.indexes.json):
  1. `audit_logs`: `(evidence_id ASC, sequence_number ASC)`
  2. `custody_transactions`: `(evidence_id ASC, status ASC)`
  3. `custody_transactions`: `(evidence_id ASC, created_at DESC)`
  4. `reports`: `(case_id ASC, generated_at DESC)`
  5. `cases`: `(is_deleted ASC, created_at DESC)`
- **Safeguard:** Preflight checklist mandates executing `firebase deploy --only firestore:indexes` and confirming all 5 indexes reach `READY` status before running any functional benchmarks.

### 4. End-to-End Workflow Route Coverage
The existing MongoDB source contains 6 documents (`evidence: 2`, `audit_logs: 3`, `blockchain_checkpoints: 1`), leaving `cases`, `reports`, and `custody_transactions` empty.
- **Coverage Mandate:** Staging validation must not rely solely on the 6 migrated documents. It must include synthetic staging operations:
  * Create & list cases (`/api/cases`)
  * Ingest evidence (`/api/evidence/upload`)
  * Execute custody transfer & acknowledgment (`/api/custody/transfer`, `/api/custody/acknowledge`)
  * Anchor on blockchain (`/api/blockchain/register`)
  * Generate & download forensic PDF reports (`/api/reports/generate`, `/api/reports/{id}`)
  * Reconcile recovery state (`/api/recovery/reconcile`)

---

## 5. Non-Destructive Test Execution & Baseline Verification

The following non-destructive test suites were executed to verify baseline stability:

| Test Suite | Scope | Executed Command | Results |
| :--- | :--- | :--- | :---: |
| **Adapter, Migration & Audit Suite** | Emulator CRUD, transactions, lease fencing, idempotency, secret patterns | `pytest -v tests/test_firestore_adapter.py tests/test_migration_script.py tests/test_audit_security.py` | **35 / 35 PASSED** (5.47s) |
| **Security & RBAC Suite** | JWT tokens, bcrypt hashes, permissions, path traversal blocks | `pytest -v tests/test_security_regression.py tests/test_rbac_regression.py` | **33 / 33 PASSED** (20.41s) |
| **Authoritative MongoDB State** | Database `chainvault` counts and audit hashes | PyMongo verification script | **100% UNTOUCHED** (6 records, 3 hashes intact) |

---

## 6. Staging Execution Checklist

Prior to initiating live staging cutover, the following prerequisites must be confirmed:

- [ ] 1. GCP Project `chainvault-staging` created (isolated from production).
- [ ] 2. Cloud Firestore enabled in Native Mode, Database ID `(default)`, in chosen region.
- [ ] 3. Service account `chainvault-backend-sa` created with role `roles/datastore.user`.
- [ ] 4. Service account key downloaded to `secrets/chainvault-staging-sa.json` (verified ignored by `.gitignore`).
- [ ] 5. Administrator runs `npx firebase-tools login` and `npx firebase-tools use chainvault-staging`.
- [ ] 6. Administrator runs `npx firebase-tools deploy --only firestore:rules` (deploys `allow read, write: if false;`).
- [ ] 7. Administrator runs `npx firebase-tools deploy --only firestore:indexes` (deploys 5 composite indexes).
- [ ] 8. Confirm all 5 indexes status is `READY` in Firebase Console.
- [ ] 9. Authorize Phase 4C live cloud staging execution.

---

## 7. Recommendation: **GO (for Cloud Staging Setup Approval)**

All preflight security controls, tooling requirements, `.gitignore` secret protections, index specifications, and cloud migration safety architectures have been authored, validated, and verified without defects.

**Operational Boundary Enforced:**
Execution stops here. `DATABASE_BACKEND=mongodb` remains active. No cloud resources have been created, no cloud migrations have been performed, and no live traffic has been diverted.
