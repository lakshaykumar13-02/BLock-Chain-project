# ChainVault Phase 4A: Staging Cutover Readiness Audit — Audit Only

## 1. Executive Summary & Objective

**Repository:** `D:\parjaayi project\CHAINVAULT`  
**Phase:** 4A — Staging Cutover Readiness Audit (Audit Only)  
**Target Milestone:** Preparation for staging validation of Google Cloud Firestore persistence adapter without compromising the primary MongoDB database (`chainvault`), physical evidence files, forensic reports, or blockchain state.

This audit evaluates the architectural readiness, query semantics, concurrency mechanisms, security posture, configuration requirements, test coverage, and rollback procedures necessary for a controlled staging cutover from MongoDB to Firebase Cloud Firestore.

**Verdict:** **GO (with explicit prerequisites)** for staging deployment preparation.

---

## 2. Files Inspected & Code Modifications

**Total Code Changes Made During Phase 4A:** **ZERO (0)** lines changed in the application codebase. `DATABASE_BACKEND=mongodb` remains active.

### Key Files Inspected:
1. [`backend/app/database/base.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/base.py): Base class defining abstract methods for client and collection adapters.
2. [`backend/app/database/firestore.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py): Async Firestore adapter, collection proxy, cursor emulator, and `@async_transactional` custody lease handlers.
3. [`backend/app/database/mongodb.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/mongodb.py): Multi-backend client factory (`get_database_client`) and default MongoDB connection lifecycle.
4. [`backend/app/database/__init__.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/__init__.py): Package-level exports for database abstraction layer.
5. [`backend/app/main.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/main.py): Application lifespan, production preflight configuration validation, CORS middleware, security headers, and router mounting.
6. [`backend/app/routes/auth.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/auth.py): Authentication endpoint, in-memory `DEMO_USERS` hash verification, and JWT issuance.
7. [`backend/app/routes/cases.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/cases.py): Case CRUD operations, soft-deletion filters (`is_deleted != True`).
8. [`backend/app/routes/evidence.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/evidence.py): Evidence ingestion, physical binary decoupling, metadata persistence.
9. [`backend/app/routes/custody.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/custody.py): Custody transfer handshakes, lock acquisition, acknowledgment, and transaction logs.
10. [`backend/app/services/custody_transaction.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/services/custody_transaction.py): Distributed lease locking, CAS updates, fencing tokens.
11. [`backend/app/services/audit_trail.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/services/audit_trail.py): Deterministic canonical SHA-256 event representation and hash verification.
12. [`backend/app/services/storage.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/services/storage.py): Decoupled evidence binary filesystem storage paths.
13. [`backend/app/services/report.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/services/report.py): Forensic report PDF generation and storage paths.
14. [`firestore.indexes.json`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.indexes.json): Composite index definitions for Cloud Firestore queries.
15. [`.env.example`](file:///d:/parjaayi%20project/CHAINVAULT/.env.example): Environment variable definitions and deployment configuration templates.

---

## 3. Query, Update, and Index Equivalence Analysis

### Application Query Operator Inventory

| Query Operator | Context in Application | MongoDB Implementation | Firestore Adapter Implementation | Cloud Firestore Compatibility Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Direct Equality (`==`)** | `evidence_id`, `case_id`, `event_id`, `report_id`, `checkpoint_id` | `collection.find_one({"field": val})` | Direct document lookup `col.document(id).get()` via `PRIMARY_KEYS` mapping | **100% Equivalent.** Fast $O(1)$ single-document reads. |
| **Inequality (`$ne`)** | `cases.is_deleted` in `GET /api/cases` | `cases.find({"is_deleted": {"$ne": True}})` | `query.where(filter=FieldFilter("is_deleted", "!=", True))` | **Semantic Difference:** Cloud Firestore inequalities require the field to exist on the document. Documents missing `is_deleted` are excluded. *Mitigation:* `POST /api/cases` explicitly sets `"is_deleted": False` upon creation. |
| **Set Membership (`$in`)** | `custody_transactions.status` | `find_one({"evidence_id": id, "status": {"$in": active}})` | `query.where(filter=FieldFilter("status", "in", active))` | **100% Equivalent.** Firestore supports up to 30 elements in `in` filter. ChainVault uses 2-3 statuses. |
| **Range (`<`, `>`)** | Custody lock expiration comparison | `expires_at < now` | Evaluated inside atomic transaction or via `FieldFilter("<", val)` | **100% Equivalent.** |
| **Cursor Sorting** | `audit_logs` (`sequence_number ASC`), `custody_transactions` (`created_at DESC`) | `.sort("field", direction)` | Memory sort in `FirestoreCursor._fetch()` | **100% Equivalent for small sets.** For production datasets > 1,000 documents, query-level ordering with indexes is recommended. |
| **Upsert (`upsert=True`)** | `cases`, `evidence`, `blockchain_checkpoints` | `update_one(..., upsert=True)` | `doc_ref.set(payload, merge=True)` | **100% Equivalent.** Replaces or merges into existing document atomically. |
| **Increment (`$inc`)** | Fencing version `custody_version` | `update_one({"$inc": {"custody_version": 1}})` | `firestore.Increment(1)` | **100% Equivalent.** Native atomic integer increment in Firestore. |

### Composite Indexes Review (`firestore.indexes.json`)

All 5 multi-field queries in the application are mapped to definitions in [`firestore.indexes.json`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.indexes.json):
1. `audit_logs`: `(evidence_id ASC, sequence_number ASC)`
2. `custody_transactions`: `(evidence_id ASC, status ASC)`
3. `custody_transactions`: `(evidence_id ASC, created_at DESC)`
4. `reports`: `(case_id ASC, generated_at DESC)`
5. `cases`: `(is_deleted ASC, created_at DESC)`

*Deployment Requirement:* In real Google Cloud Firestore, these composite indexes must be deployed using `firebase deploy --only firestore:indexes`. The emulator permits unindexed queries with warnings, but real Cloud Firestore strictly rejects them with HTTP 400 (`FAILED_PRECONDITION`).

---

## 4. Atomic Concurrency, Leases, and Fencing Analysis

ChainVault's custody transfer workflow requires strict concurrency control to prevent split-brain custody handshakes and race conditions.

### Concurrency Implementation Comparison

| Mechanism | MongoDB Implementation | Firestore Persistence Implementation | Verification Status |
| :--- | :--- | :--- | :---: |
| **Atomic Lease Acquisition** | `update_one()` with `$or` filter condition on unexpired lease | Firestore `@async_transactional` atomic transaction with read-before-write check | **VERIFIED** in `test_live_emulator_concurrency_lease_and_fencing` |
| **Lock Token Identity** | Cryptographic UUIDv4 token stored in `transfer_lock.lock_token` | Same UUIDv4 token stored in `transfer_lock.lock_token` | **VERIFIED** |
| **Lease Expiration Recovery** | If `now > transfer_lock.expires_at`, lock is stealable | Read in transaction checks `curr_lock["expires_at"] > now`; overwrites if expired | **VERIFIED** in `test_live_emulator_lease_expiration_and_fencing_rejection` |
| **Fencing Version Token** | Monotonically increasing `custody_version` integer | Verified against `expected_version` before CAS commit; incremented via `firestore.Increment(1)` | **VERIFIED** |
| **Stale Worker Rejection** | Stale worker write rejected due to mismatched version or expired lock token | Transaction rolls back if `current_ver != expected_version` or lock token mismatch | **VERIFIED** |
| **Idempotency De-duplication** | Unique index on `idempotency_records.idempotency_key` | Deterministic document ID in `idempotency_records` collection with cached response check | **VERIFIED** in `test_live_emulator_idempotency_and_state_recovery` |

---

## 5. Dataset & Test Coverage Gap Analysis

### Current Dataset State
The authoritative MongoDB source `chainvault` and the migrated Firestore dataset contain **6 records**:
- `evidence`: 2 records (`EV-PH4-001`, `EV-PH4-DEBUG`)
- `audit_logs`: 3 records (`EVT-EV-PH4-DEBUG-0001-2F5306`, `EVT-EV-PH4-001-0001-F34E97`, `EVT-EV-PH4-001-0002-859D19`)
- `blockchain_checkpoints`: 1 record (`CHK-EV-PH4-001`)
- `cases`: 0 records
- `reports`: 0 records
- `custody_transactions`: 0 records
- `idempotency_records`: 0 records
- `users`: 0 records (auth uses in-memory `DEMO_USERS` with bcrypt hashes)

### Identified Gaps Before Staging Acceptance
1. **Case Management Coverage:** Zero historical cases exist. Full lifecycle testing (`create_case`, `list_cases`, `get_case`, `soft_delete_case`) must be validated with synthetic staging cases.
2. **Custody Transfer Flow:** Zero historical custody transactions exist. Full transfer handshake (`transfer_custody` &rarr; `acknowledge_custody` &rarr; audit trail generation) must be validated.
3. **Forensic PDF Reports:** Zero database report records exist. Report generation against Firestore metadata must be tested to ensure PDF paths and SHA-256 hashes persist correctly.
4. **Idempotency Replay:** Idempotency cache recovery must be tested through repeated API submissions with identical keys.

---

## 6. Verified Facts vs. Assumptions

### Verified Facts (Empirically Proven)
1. **Contract Equivalence:** The `FirestoreClient` and `FirestoreCollectionAdapter` satisfy the full `BaseDatabaseClient` interface without runtime errors.
2. **Local Emulator Parity:** 32 adapter and migration tests pass against the local emulator on port 8080.
3. **Cryptographic Invariance:** Canonical SHA-256 event hashing produces bit-for-bit identical hashes across MongoDB and Firestore using RFC 3339 UTC string normalization.
4. **Decoupled Storage:** Binary evidence files and forensic PDFs remain on disk and are never uploaded to Firestore.
5. **Persistence & Cold Boot:** The Firestore emulator state survives process termination and reloads 100% of data when booted with `--seed_from_export`.
6. **Regression Suite:** All 36 security, RBAC, and configuration audit regression tests pass.

### Unverified Assumptions (To Be Validated in Real Cloud Staging)
1. **Network Latency:** Emulator response latency is <1ms. Real Cloud Firestore HTTPS/gRPC latency is 15-50ms per round trip; transactions with retries will take longer.
2. **IAM Token Lifecycles:** In the emulator, OAuth2 token renewal is bypassed. In Google Cloud, service account credentials must be verified for automatic token rotation.
3. **Index Preconditions:** The emulator logs warnings for missing composite indexes; Cloud Firestore rejects unindexed queries with HTTP 400.
4. **Concurrency Hotspots:** Cloud Firestore imposes a limit of 1 write/second per document. Concurrent write bursts on a single evidence item will experience transaction contention retries.

---

## 7. Security, IAM, and Network Architecture

### Client-Side Security & Rules
- **Backend Architecture:** ChainVault is a server-side API application. Browser clients communicate exclusively with the FastAPI backend over TLS (`/api/...`).
- **Client SDKs:** Browsers **never** connect directly to Firestore.
- **Firestore Security Rules:** In Cloud Firestore, client-side access must be disabled completely via `firestore.rules`:
  ```javascript
  rules_version = '2';
  service cloud.firestore {
    match /databases/{database}/documents {
      match /{document=**} {
        allow read, write: if false;
      }
    }
  }
  ```
  The backend connects using the Google Cloud Admin / Server SDK with service account credentials, which automatically bypasses security rules.

### IAM & Least Privilege
The backend service account requires only:
- `roles/datastore.user` (Cloud Datastore User: Read/Write access to Firestore data)
- It **must not** possess `roles/owner` or `roles/editor`.

---

## 8. Staged Cutover & Rollback Plan

### Stage 1: Preflight & Staging Cloud Setup
1. Create isolated Google Cloud project `chainvault-staging` (do not use production).
2. Create Firestore database in Native Mode (`(default)` in region `asia-south1` or `us-central1`).
3. Deploy composite indexes: `firebase deploy --only firestore:indexes`.
4. Deploy locked security rules: `firebase deploy --only firestore:rules`.
5. Generate service account keyfile and grant `roles/datastore.user`.

### Stage 2: Staging Data Seeding
1. Migrate the 6 verified metadata records using `scripts/migrate_mongo_to_firestore.py` pointing to staging Firestore.
2. Execute dual-read verification to assert 100% parity with MongoDB.

### Stage 3: Isolated Staging Execution
1. Deploy a dedicated staging backend instance configured with:
   - `ENVIRONMENT=staging`
   - `DATABASE_BACKEND=firestore`
   - `FIREBASE_PROJECT_ID=chainvault-staging`
   - `GOOGLE_APPLICATION_CREDENTIALS=/path/to/staging-sa.json`
2. Run end-to-end synthetic functional tests across all endpoints (Cases, Evidence, Custody, Audit, Reports).

### Stage 4: Rollback Procedure (Zero Downtime, Zero Data Loss)
If any anomaly, latency spike, or query rejection occurs during staging:
1. Revert environment variable: `DATABASE_BACKEND=mongodb`.
2. Restart backend service.
3. MongoDB remains the authoritative source of truth. Zero records were modified or deleted.

---

## 9. Staging Cutover Readiness Verdict: **GO**

All adapter code, transactional semantics, index specifications, and non-destructive read-only tests confirm that ChainVault is architecturally ready for controlled staging deployment.

**Safety Enforcement:** The active database backend remains `DATABASE_BACKEND=mongodb`. Cloud resources must not be created until authorized.
