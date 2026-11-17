# ChainVault Phase 4C — Cloud Staging Configuration Validation Report
**Document ID:** `docs/audit/PHASE_4C_CLOUD_CONFIGURATION_VALIDATION.md`  
**Execution Timestamp:** 2026-10-24T16:32:00+05:30  
**Phase:** Phase 4C — Cloud Staging Configuration Validation (NO MIGRATION, NO AUTOMATIC DEPLOYMENT)  
**Target Environment:** Firebase Staging (`chainvault-staging`)  
**Database:** Cloud Firestore `(default)` (Standard Edition)  
**Authoritative Source:** MongoDB `chainvault` (Local, Read-Only, 100% Preserved)  
**Active Backend Engine:** `DATABASE_BACKEND=mongodb` (Unchanged)  

---

## 1. Executive Summary & Audit Scope

Following the successful creation of the Cloud Firestore `(default)` database in the Firebase Console for staging project `chainvault-staging`, Phase 4C executed a comprehensive, non-destructive configuration validation.

In accordance with strict staging preflight directives:
- **Zero Cloud Mutations:** No rules or indexes were automatically deployed to the cloud.
- **Zero Data Migration:** No data was migrated from MongoDB to Cloud Firestore.
- **Zero Configuration Drift:** The application's runtime configuration remains locked to `DATABASE_BACKEND=mongodb`.
- **Zero Secret Exposure:** No service account keys, tokens, private keys, or credentials were created, printed, or staged in Git.
- **Authoritative Preservation:** All 6 authoritative records in MongoDB database `chainvault`, all physical evidence files, forensic reports, and blockchain state were verified 100% intact.

---

## 2. Configuration Files & Security Posture Audit

### 2.1 `firebase.json`
- **Location:** [firebase.json](file:///D:/parjaayi%20project/CHAINVAULT/firebase.json)
- **Validation Result:** **VALID**
- **Contents:**
  ```json
  {
    "firestore": {
      "rules": "firestore.rules",
      "indexes": "firestore.indexes.json"
    },
    "emulators": {
      "firestore": {
        "port": 8080,
        "host": "127.0.0.1"
      },
      "ui": {
        "enabled": false
      }
    }
  }
  ```
- **Findings:**
  1. The `"firestore"` stanza links directly to `firestore.rules` and `firestore.indexes.json` in the project root.
  2. The local emulator stanza remains explicitly bound to `127.0.0.1:8080` (loopback only), ensuring offline emulator operations remain isolated from cloud operations.

### 2.2 `.firebaserc`
- **Location:** [.firebaserc](file:///D:/parjaayi%20project/CHAINVAULT/.firebaserc)
- **Validation Result:** **VALID**
- **Contents:**
  ```json
  {
    "projects": {
      "default": "chainvault-staging",
      "staging": "chainvault-staging"
    }
  }
  ```
- **Findings:**
  1. Explicitly defines `chainvault-staging` as both the `default` and `staging` project aliases.
  2. Eliminates any ambiguity when running Firebase CLI commands, preventing accidental execution against personal or production Google Cloud projects.

### 2.3 `firestore.rules` (Client SDK Denial & Admin SDK Bypass)
- **Location:** [firestore.rules](file:///D:/parjaayi%20project/CHAINVAULT/firestore.rules)
- **Validation Result:** **VALID & SECURE**
- **Contents:**
  ```javascript
  rules_version = '2';
  service cloud.firestore {
    match /databases/{database}/documents {
      // ChainVault Security Posture:
      // Client SDK access is completely denied to enforce that all database operations
      // must route exclusively through the FastAPI backend authenticated via JWT/RBAC.
      // The backend connects via the Google Cloud Server SDK using service account IAM roles,
      // which automatically bypasses client-side security rules.
      match /{document=**} {
        allow read, write: if false;
      }
    }
  }
  ```
- **Security Analysis:**
  1. **Direct Client Denial:** `match /{document=**} { allow read, write: if false; }` recursively matches every document across all collections. All direct Web, iOS, and Android client SDK calls (`get`, `list`, `create`, `update`, `delete`) are rejected unconditionally with `PERMISSION_DENIED`.
  2. **Zero Direct Access:** Direct client database access is completely eliminated. All requests must transit the FastAPI backend where JWT authentication, cryptographic signatures, and role-based access control (RBAC) are strictly enforced.
  3. **Backend Admin Access Preservation:** Google Cloud Firestore server-side SDKs (`google-cloud-firestore` for Python AsyncClient, Node.js Admin SDK, etc.) authenticate using Google Cloud IAM credentials (service account with `roles/datastore.user`). Per Cloud Firestore architecture, server SDKs operate outside security rules and are unaffected by client denial rules.

### 2.4 `firestore.indexes.json` (Composite Indexes Audit)
- **Location:** [firestore.indexes.json](file:///D:/parjaayi%20project/CHAINVAULT/firestore.indexes.json)
- **Validation Result:** **VALID & COMPLETE**
- **Contents:**
  ```json
  {
    "indexes": [
      {
        "collectionGroup": "audit_logs",
        "queryScope": "COLLECTION",
        "fields": [
          { "fieldPath": "evidence_id", "order": "ASCENDING" },
          { "fieldPath": "sequence_number", "order": "ASCENDING" }
        ]
      },
      {
        "collectionGroup": "custody_transactions",
        "queryScope": "COLLECTION",
        "fields": [
          { "fieldPath": "evidence_id", "order": "ASCENDING" },
          { "fieldPath": "status", "order": "ASCENDING" }
        ]
      },
      {
        "collectionGroup": "custody_transactions",
        "queryScope": "COLLECTION",
        "fields": [
          { "fieldPath": "evidence_id", "order": "ASCENDING" },
          { "fieldPath": "created_at", "order": "DESCENDING" }
        ]
      },
      {
        "collectionGroup": "reports",
        "queryScope": "COLLECTION",
        "fields": [
          { "fieldPath": "case_id", "order": "ASCENDING" },
          { "fieldPath": "generated_at", "order": "DESCENDING" }
        ]
      },
      {
        "collectionGroup": "cases",
        "queryScope": "COLLECTION",
        "fields": [
          { "fieldPath": "is_deleted", "order": "ASCENDING" },
          { "fieldPath": "created_at", "order": "DESCENDING" }
        ]
      }
    ],
    "fieldOverrides": []
  }
  ```

#### Detailed Query-to-Index Cross-Reference:
| Collection | Fields & Sort Orders | Application Code Source | Query Pattern | Necessity Status |
| :--- | :--- | :--- | :--- | :--- |
| `audit_logs` | `evidence_id ASC`, `sequence_number ASC` | [`backend/app/services/audit_trail.py:156-159`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/services/audit_trail.py#L156-L159) | `audit_logs.find({"evidence_id": id}).sort("sequence_number", 1)` | **REQUIRED**. Cloud Firestore rejects equality filter + different order field without this index (`FAILED_PRECONDITION`). |
| `custody_transactions` | `evidence_id ASC`, `status ASC` | [`backend/app/services/custody_transaction.py:181-184`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/services/custody_transaction.py#L181-L184) | `custody_transactions.find_one({"evidence_id": id, "status": {"$in": [...]}})` | **REQUIRED**. Multi-field equality/`in` query across distinct attributes requires composite index in Cloud Firestore. |
| `custody_transactions` | `evidence_id ASC`, `created_at DESC` | [`backend/app/routes/custody.py:663`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/routes/custody.py#L663) | `custody_transactions.find({"evidence_id": id}).sort("created_at", -1)` | **REQUIRED**. Equality filter + descending sort field requires composite index in Cloud Firestore. |
| `reports` | `case_id ASC`, `generated_at DESC` | [`backend/app/routes/reports.py:643`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/routes/reports.py#L643) | `reports.find({"case_id": id}).sort("generated_at", -1)` | **REQUIRED / PREVENTATIVE**. Case forensic reports listed in reverse-chronological order. |
| `cases` | `is_deleted ASC`, `created_at DESC` | [`backend/app/routes/cases.py:73`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/routes/cases.py#L73) | `cases.find({"is_deleted": {"$ne": True}})` | **REQUIRED / PREVENTATIVE**. Active case listing filtered by soft-deletion and ordered by timestamp. |

- **Unsupported Query Semantics Check:**
  - Cloud Firestore forbids inequality operators (`!=`, `<`, `>`, `<=`, `>=`) on *more than one distinct field* in a single query.
  - Verification confirmed that ChainVault queries never combine inequalities across different fields.
  - Complex `$or` expressions for distributed lease expiration are safely handled in Python snapshot inspection within atomic transactions ([`backend/app/database/firestore.py:302-334`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py#L302-L334)) and `@async_transactional` methods ([`backend/app/database/firestore.py:560-718`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py#L560-L718)).
- **Missing or Unnecessary Indexes:**
  - Zero missing indexes.
  - Zero redundant or unnecessary indexes.

### 2.5 `.gitignore` Hardening & Secret Protection
- **Location:** [.gitignore](file:///D:/parjaayi%20project/CHAINVAULT/.gitignore)
- **Validation Result:** **HARDENED & SECURE**
- **Protected Patterns:**
  - `*.pem`, `*.key`
  - `*service_account*.json`, `*service-account*.json`
  - `*credentials*.json`
  - `secrets/`, `backend/secrets/`
  - `firebase-debug.log*`, `firestore-debug.log*`, `ui-debug.log*`
- **Git Repository Audit:** Executed `git status` and file tracking audit; confirmed zero secret keyfiles, service account JSON files, or `.env` files are tracked in Git.

### 2.6 `.env.example`
- **Location:** [.env.example](file:///D:/parjaayi%20project/CHAINVAULT/.env.example)
- **Validation Result:** **VALID**
- **Settings:**
  ```ini
  ENVIRONMENT=staging
  REQUIRE_PERSISTENT_STORAGE=true
  DATABASE_BACKEND=mongodb
  FIREBASE_PROJECT_ID=chainvault-staging
  FIRESTORE_DATABASE_ID=(default)
  # GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
  # FIRESTORE_EMULATOR_HOST=localhost:8080
  ```
- **Findings:** `DATABASE_BACKEND=mongodb` remains the documented and default active backend, ensuring MongoDB remains primary until full staging validation is complete.

---

## 3. Firebase CLI Tooling & Authentication Status

A live check was conducted using the local Firebase CLI:

1. **CLI Version:**
   - Command: `npx --yes firebase-tools --version`
   - Output: `15.34.1`
   - Status: Installed and operational via Node.js runtime.

2. **Authentication Status:**
   - Command: `npx --yes firebase-tools login:list`
   - Output:
     ```
     ! No authorized accounts, run "firebase login"
     ```
   - Status: **UNAUTHENTICATED (Expected in CI/Local preflight)**.

3. **Active Project Verification:**
   - Command: `npx --yes firebase-tools use`
   - Output:
     ```
     Error: Failed to authenticate, have you run firebase login?
     ```
   - Status: **CONFIRMED UNLINKED UNTIL LOGIN**.
   - Analysis: While `.firebaserc` binds the alias to `chainvault-staging`, Firebase CLI commands require an active OAuth token or service account environment before they can communicate with Google Cloud APIs.

---

## 4. Emulator-Only Migration Script Safeguards Verification

- **Script:** [`backend/scripts/migrate_mongo_to_firestore.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py)
- **Safeguards Audit Result:** **100% INTACT & RIGID**

### Active Safety Controls:
1. **Host Loopback Restriction ([lines 144-166](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L144-L166)):**
   - Strictly enforces that `FIRESTORE_EMULATOR_HOST` must resolve to `127.0.0.1`, `localhost`, or `::1`. Any non-loopback host immediately raises a fatal `RuntimeError("SAFETY VIOLATION")`.
2. **Prohibited Project Names ([lines 145, 167-175](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L145-L175)):**
   - Rejects any target project name containing `prod`, `production`, `live`, or `mainnet`.
3. **TCP Socket Probe ([lines 177-186](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L177-L186)):**
   - Verifies local TCP socket connectivity on port 8080 before initializing any Firestore client.
4. **Dry-Run by Default ([lines 555-559](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L555-L559)):**
   - Executes strictly in simulation mode unless `--execute` is explicitly supplied.
5. **Storage Decoupling ([lines 230-234](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L230-L234)):**
   - Rejects binary payloads with `TypeError`. Physical evidence files and PDFs remain strictly on disk.
6. **Conflict Detection ([lines 521-536](file:///D:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L521-L536)):**
   - Refuses to overwrite destination records if diffs are detected, reporting conflicts in the audit manifest.

---

## 5. Exact Deployment Commands (For Reviewed Deployment)

The operator must execute the following commands **interactively** in a terminal when ready to deploy the rules and indexes to `chainvault-staging`. 

> [!CAUTION]
> **DO NOT DEPLOY AUTOMATICALLY.** These commands must be reviewed and executed manually by the authorized Google Cloud project administrator.

### Step 1: Authenticate Firebase CLI
```bash
npx firebase-tools login
```
*Expected prompt: Browser window opens to authenticate Google Cloud account with access to `chainvault-staging`.*

### Step 2: Confirm Active Project
```bash
npx firebase-tools use chainvault-staging
```
*Expected output: `Active project: chainvault-staging`.*

### Step 3: Deploy Firestore Security Rules
```bash
npx firebase-tools deploy --only firestore:rules --project chainvault-staging
```
*Expected output: `✔  firestore: released rules firestore.rules to cloud.firestore`.*

### Step 4: Deploy Firestore Composite Indexes
```bash
npx firebase-tools deploy --only firestore:indexes --project chainvault-staging
```
*Expected output: `✔  firestore: deployed indexes in firestore.indexes.json successfully`.*

### Step 5: Verify Deployment Status in Cloud Console / CLI
```bash
npx firebase-tools firestore:indexes --project chainvault-staging
```
*Expected output: Listing of the 5 composite indexes showing status `READY` (building takes ~1-3 minutes in Cloud Firestore).*

---

## 6. Local Test Suite & Non-Destructive Validation Results

All tests were executed locally against the active environment:

```powershell
backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_firestore_adapter.py backend/tests/test_migration_script.py backend/tests/test_audit_security.py
```
**Result:** **35 passed in 5.45s** (100% PASS)

```powershell
backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_custody_audit_trail.py backend/tests/test_evidence_integrity_suite.py
```
**Result:** **45 passed in 36.84s** (100% PASS)

### Summary of Passing Test Assertions:
1. `test_firestore_client_instantiation`: Verified async initialization and configuration.
2. `test_database_backend_selection`: Verified backend switching logic between MongoDB and Firestore.
3. `test_fail_closed_when_persistent_storage_required`: Verified strict fail-closed behavior on storage failure.
4. `test_canonical_event_hashing_exact_preservation`: Verified RFC 3339 timestamps and SHA-256 hash invariance.
5. `test_storage_separation_metadata_only`: Verified binary files are never stored in database metadata.
6. `test_deterministic_document_id_mapping`: Verified 1:1 primary key determinism across all collections.
7. `test_lease_fencing_version_check_logic`: Verified distributed custody lease fencing and OCC version bumps.
8. `test_safety_guard_rejects_missing_or_cloud_hosts`: Verified migration script refuses cloud targets.
9. `test_safety_guard_rejects_production_project_names`: Verified migration script rejects production project IDs.
10. `test_idempotent_rerun_skips_identical_records`: Verified migration script idempotency.
11. `test_gitignore_protects_evidence_and_reports`: Verified repository ignores secrets and evidence binaries.
12. Custody & Evidence Suites (45 tests): Verified Merkle chains, blockchain anchor consistency, and tamper detection.

---

## 7. Authoritative Database State Verification

A non-destructive query to local MongoDB `chainvault` verified that zero modifications took place during Phase 4C:

| Collection | Authoritative Document Count | Status |
| :--- | :--- | :--- |
| `idempotency_records` | 0 | Untouched |
| `audit_logs` | 3 | Untouched |
| `cases` | 0 | Untouched |
| `evidence` | 2 | Untouched |
| `blockchain_checkpoints` | 1 | Untouched |
| `reports` | 0 | Untouched |
| **Total** | **6 records** | **100% Exact Invariance** |

---

## 8. Blockers & Pending Prerequisites Checklist

| Item | Prerequisite | Current Status | Blocker? | Required Action |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Firestore `(default)` Database | **CREATED** | No | Completed in Firebase Console by operator. |
| 2 | Configuration Files (`firebase.json`, `.firebaserc`, `rules`, `indexes`) | **VALIDATED** | No | Ready for reviewed deployment. |
| 3 | Firebase CLI Tooling | **INSTALLED** (v15.34.1) | No | Ready. |
| 4 | Firebase CLI Authentication | **UNAUTHENTICATED** | **YES** | Operator must run `npx firebase-tools login`. |
| 5 | Cloud Staging Rules & Indexes Deployment | **NOT DEPLOYED** | **HOLD** | Awaiting manual deployment after CLI authentication. |
| 6 | Cloud Service Account Key | **NOT CREATED** | **HOLD** | Required only for backend Cloud Firestore connection; not needed for rules deployment. |
| 7 | Data Migration to Cloud | **BLOCKED** | **HOLD** | Script remains emulator-restricted until separate cloud migration tool authorization. |

---

## 9. Conclusion & Phase Gate Sign-Off

**Phase 4C Status:** **VALIDATION COMPLETE — READY FOR REVIEWED DEPLOYMENT**

All local configuration files, security rules, composite indexes, secret protections, and script safeguards have been thoroughly validated against the actual codebase and real Cloud Firestore semantic requirements. 

Execution has stopped prior to any cloud deployment or data migration, pending human operator authentication and review.
