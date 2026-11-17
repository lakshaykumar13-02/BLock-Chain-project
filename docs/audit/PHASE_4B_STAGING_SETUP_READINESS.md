# ChainVault Phase 4B — Controlled Firebase Cloud Staging Setup Readiness Report

**Authoritative Repository:** `D:\parjaayi project\CHAINVAULT`  
**Current Active Backend:** `DATABASE_BACKEND=mongodb` (Unchanged & Authoritative)  
**Execution Mode:** Configuration and Staging Readiness Planning Audit (Cloud Creation Hold Active)  
**Date:** 2026-10-24

---

## 1. Executive Summary & Objective

Phase 4B establishes the formal staging environment blueprint, security configurations, deployment commands, risk assessments, and rollback mechanisms required to validate Google Cloud Firestore as ChainVault's database backend without risking production integrity or compromising the authoritative MongoDB database (`chainvault`).

In compliance with **Mandatory Safety Constraint 7**, because live Google Cloud service-account credentials and explicit cloud resource creation approvals have not yet been provisioned, this phase executes as a **planning and configuration readiness audit**. Zero cloud resources were created, zero billable services were provisioned, and MongoDB remains the active authoritative backend.

---

## 2. Staging Resource Checklist & Prerequisites

Prior to conducting any staging execution or cutover validation, the following cloud prerequisites must be established in Google Cloud Platform (GCP):

| Resource / Prerequisite | Target Specification | Purpose & Least-Privilege Requirement | Verification Status |
| :--- | :--- | :--- | :---: |
| **Dedicated GCP Project** | `chainvault-staging` (Non-production) | Complete blast-radius isolation from production workloads and billing accounts. | **Prerequisite (Awaiting GCP Setup)** |
| **Firestore Database** | Native Mode, Database ID `(default)` | Document database engine with ACID transactions and collection indexing. Region: `asia-south1` (Mumbai) or project-preferred region. | **Prerequisite (Awaiting GCP Setup)** |
| **Service Account** | `chainvault-backend-sa@chainvault-staging.iam.gserviceaccount.com` | Least-privilege IAM service account for backend API access. Required Role: `roles/datastore.user` strictly. Prohibit `roles/owner` or `roles/editor`. | **Prerequisite (Awaiting GCP Setup)** |
| **Service Account Key** | JSON keyfile stored securely outside Git (e.g. `backend/secrets/staging-sa.json`) | Provides credentials for `GOOGLE_APPLICATION_CREDENTIALS`. File must be added to `.gitignore`. | **Prerequisite (Awaiting GCP Setup)** |
| **Security Rules** | `firestore.rules` deployed with `allow read, write: if false;` | Rejects all direct browser/mobile client SDK access; forces all access through FastAPI backend. | **READY** in [`firestore.rules`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.rules) |
| **Composite Indexes** | 5 composite index definitions deployed from `firestore.indexes.json` | Satisfies composite query requirements for `audit_logs`, `custody_transactions`, `reports`, and `cases`. | **READY** in [`firestore.indexes.json`](file:///d:/parjaayi%20project/CHAINVAULT/firestore.indexes.json) |
| **Restricted CORS** | Explicit staging frontend origins only (e.g. `http://localhost:3000,http://staging.chainvault.internal`) | Prevents cross-origin browser abuse. Wildcards (`*`) strictly rejected by security preflight. | **READY** in [`backend/app/main.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/main.py#L92-L112) |
| **Dedicated Testnet RPC** | Local Hardhat node (`http://127.0.0.1:8545`) or Sepolia testnet RPC | Prohibits mainnet blockchain interaction during staging. | **READY** |

---

## 3. Safe Environment-Variable Template (Staging)

The following template defines the configuration required for staging. In compliance with security rules, placeholder templates are shown; real secrets, keys, and credentials must never be committed to Git.

```dotenv
# =============================================================================
# ChainVault Staging Environment Configuration (.env.staging)
# =============================================================================

# 1. Operational Mode
ENVIRONMENT=staging
REQUIRE_PERSISTENT_STORAGE=true

# 2. Database Backend Selection
# Set to 'firestore' to activate the Cloud Firestore adapter during staging tests
DATABASE_BACKEND=firestore

# 3. Google Cloud / Firebase Staging Configuration
FIREBASE_PROJECT_ID=chainvault-staging
FIRESTORE_DATABASE_ID=(default)
# Absolute or relative path to the least-privilege service account keyfile:
GOOGLE_APPLICATION_CREDENTIALS=secrets/chainvault-staging-sa.json
# FIRESTORE_EMULATOR_HOST must remain UNSET in live staging to target Cloud Firestore

# 4. Authoritative MongoDB Reference (Retained for Instant Fallback)
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=chainvault_staging

# 5. Cryptographic Security & Authentication
# Min 32 random characters (generated via openssl rand -hex 32)
JWT_SECRET=replace_with_staging_cryptographically_secure_random_key_min_32_chars
JWT_EXPIRE_MINUTES=60

# 6. Decoupled Physical Storage Paths
STORAGE_PATH=storage/evidence
REPORTS_PATH=generated_reports

# 7. Blockchain Integration (Testnet Only)
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
BLOCKCHAIN_CHAIN_ID=31337
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3

# 8. Web Security & CORS
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
PUBLIC_VERIFICATION_URL_BASE=http://localhost:3000/verify
ALLOW_LOCAL_QR_LINKS=true
```

---

## 4. Cloud Deployment Commands & Procedures

### Step 1: Firebase Project Alignment
```bash
# Authenticate to Google Cloud (must be authorized administrator)
firebase login

# Set active project to staging project
firebase use chainvault-staging
```

### Step 2: Deploy Firestore Security Rules
```bash
# Deploys locked-down security rules that block direct client access
firebase deploy --only firestore:rules
```
*Expected Output:*
```text
✔  firestore: released rules firestore.rules to cloud.firestore
✔  Deploy complete!
```

### Step 3: Deploy Firestore Composite Indexes
```bash
# Deploys the 5 verified composite indexes defined in firestore.indexes.json
firebase deploy --only firestore:indexes
```
*Expected Output:*
```text
✔  firestore: indexes deployed successfully
```
*Note on Index Building:* Cloud Firestore builds composite indexes asynchronously across storage partitions. Index status must be checked in the Firebase Console or via `gcloud firestore indexes composite list` to ensure all 5 indexes transition from `CREATING` to `READY` before running query benchmarks.

---

## 5. Migration Tool Safety Verification

Inspection of [`backend/scripts/migrate_mongo_to_firestore.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py) reveals the following built-in safeguards:

1. **Loopback Host Guard:**
   [`validate_emulator_target()`](file:///d:/parjaayi%20project/CHAINVAULT/backend/scripts/migrate_mongo_to_firestore.py#L148-L174) rejects execution if `FIRESTORE_EMULATOR_HOST` is unset or not `127.0.0.1`, `localhost`, or `::1`. This hard gate ensures the script **cannot accidentally route writes to Google Cloud** unless an authorized cloud migration mode is explicitly invoked.
2. **Prohibited Project Names:**
   Rejects project IDs containing `prod`, `production`, `live`, or `mainnet`.
3. **Overwrite Prevention:**
   Before persisting any record, the script executes `dest_col_ref.document(doc_id).get()`.
   - If document exists and is identical: increments `already_present_count` and skips writing.
   - If document exists and differs: increments `conflict_count`, logs the deep field diff, and refuses to overwrite.
4. **Source Immutability:**
   Connects to MongoDB using `AsyncIOMotorClient` and executes only read queries (`.find()`, `.count_documents()`). It possesses zero write, update, delete, or drop commands against MongoDB.
5. **Storage Decoupling:**
   Binary files (`storage/evidence/` and `generated_reports/`) are validated for existence and SHA-256 match on local disk. Raw binary blobs are strictly excluded from Firestore payloads.

---

## 6. Authentication Architecture & Persistent Users Roadmap

### Current Architecture
ChainVault currently manages user authentication via the in-memory `DEMO_USERS` registry in [`backend/app/routes/auth.py`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/auth.py#L20-L51):
- Users: `admin`, `investigator1`, `analyst1`, `viewer1`, `suspended_user`.
- Security: Cryptographic bcrypt password hashing (`verify_password`), signed JWT access tokens (`HS256`, 60-min expiry), and role-based access control (RBAC).
- Database Status: The MongoDB `users` collection is currently empty; authentication operates independently of database persistence.

### Decision Matrix for Staging Authentication

| Architecture Option | Description | Impact on Existing Code | Recommendation |
| :--- | :--- | :--- | :--- |
| **Option A: Database-Backed Users in Firestore** | Seed `users` collection in Firestore with the 5 bcrypt-hashed user documents. Update `auth.py` to query `db_client.users.find_one({"username": req.username})`. | Minor edit to `auth.py` login route. Retains existing JWT/bcrypt semantics. | **Recommended for post-staging hardening.** |
| **Option B: Maintain In-Memory `DEMO_USERS` in Staging** | Retain in-memory `DEMO_USERS` during initial staging cutover validation. | **Zero code changes.** Focuses database staging validation strictly on evidence, custody, cases, audit logs, and reports. | **RECOMMENDED FOR PHASE 4B/4C STAGING.** |
| **Option C: Firebase Authentication** | Replace JWT/bcrypt with Firebase Auth SDK. | **STRICTLY REJECTED.** Violates Phase 1 & Phase 2 project rules: *"Database migration only. Do not replace current auth with Firebase Auth."* | **REJECTED** |

---

## 7. Concurrency, Distributed Locking & Cloud Risks

### 1. Document Write Rate Contention
- **Cloud Firestore Limit:** 1 write per second per document sustained rate.
- **Risk Scenario:** Multiple concurrent investigators attempting simultaneous custody transfers on the same evidence ID (`EV-PH4-001`).
- **Safeguard in Code:** The Firestore adapter uses native transactions with optimistic concurrency control (`@async_transactional`) in [`acquire_custody_transfer_lock()`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py#L560-L627) with backoff retries (`wait_timeout=0.4s`, `asyncio.sleep(0.02)`). Staging load testing must verify that transfer contention resolves gracefully with HTTP 409 (`LOCKED`) rather than unhandled 500 exceptions.

### 2. Network Latency Differences
- **Local Emulator:** Round-trip latency is `< 1ms`.
- **Cloud Firestore:** WAN HTTPS/gRPC latency ranges from `15ms` to `65ms`.
- **Risk Scenario:** Multi-step operations (`acquire_lock` &rarr; `blockchain_tx` &rarr; `audit_log_insert` &rarr; `release_lock`) will take slightly longer to complete in Cloud Firestore.
- **Safeguard in Code:** Lease duration is set to `30.0` seconds with renewal capability via [`renew_custody_transfer_lock()`](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py#L628-L658), providing ample safety margin over network round-trip delays.

---

## 8. Staged Cutover & Rapid Rollback Plan

```
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│     Phase 4B Setup      │ ──> │    Phase 4C Staging     │ ──> │   Phase 4D Production   │
│  Prerequisites Verified │     │  Synthetic Live Testing │     │  Final User Sign-off    │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
            │                                │
            ▼                                ▼
┌────────────────────────────────────────────────────────┐
│             INSTANT ZERO-DATA-LOSS ROLLBACK            │
│       Revert: DATABASE_BACKEND=mongodb (Restart)       │
│      MongoDB remains 100% authoritative and intact     │
└────────────────────────────────────────────────────────┘
```

### Rollback Procedure (Zero Downtime, Zero Data Loss)
If any index error, latency spike, or credential issue is encountered during staging validation:
1. Revert environment variable in `.env`: `DATABASE_BACKEND=mongodb`.
2. Restart backend process.
3. Verify `/api/health` and `/api/evidence`.
4. **Data Safety Assurance:** Authoritative MongoDB records are never deleted, dropped, or modified during staging tests. Rolling back is instantaneous and completely safe.

---

## 9. Verification Testing Results (Non-Destructive)

The following verification test suites were executed in the local environment to assert baseline stability:

| Test Suite | Scope | Executed Command | Results |
| :--- | :--- | :--- | :---: |
| **Adapter & Migration Suite** | Live Emulator CRUD, lease fencing, idempotency, migration safety | `pytest -v tests/test_firestore_adapter.py tests/test_migration_script.py` | **32 / 32 PASSED** (5.31s) |
| **Security & RBAC Suite** | JWT authentication, bcrypt passwords, role permissions, input validation | `pytest -v tests/test_security_regression.py tests/test_rbac_regression.py tests/test_audit_security.py` | **36 / 36 PASSED** (20.41s) |
| **Read-Only Endpoint Probe** | FastAPI app with `DATABASE_BACKEND=firestore` | `python test_firestore_routes_readonly.py` | **PASS** (`/health`, `/login`, `/evidence`, `/cases`) |
| **Authoritative Source State** | MongoDB collection count & audit hash verification | PyMongo verification script | **100% UNCHANGED** (6 records, 3 hashes intact) |

---

## 10. Verdict & Recommendation: **GO (for Staging Preparation)**

The configuration, security rules, indexes, and architectural interfaces for Cloud Firestore staging are verified and ready.

**Operational Boundary Enforced:**
In strict compliance with instructions:
- `DATABASE_BACKEND=mongodb` remains active.
- No Google Cloud resources have been created.
- Execution stops here. Staging cloud provisioning requires separate explicit review and authorization.
