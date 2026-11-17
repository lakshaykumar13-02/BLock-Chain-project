# ChainVault Phase 4D — Backend IAM and Authentication Readiness Audit
**Document ID:** `docs/audit/PHASE_4D_BACKEND_IAM_READINESS.md`  
**Execution Timestamp:** 2026-10-24T17:05:00+05:30  
**Phase:** Phase 4D — Backend IAM and Authentication Readiness Audit (AUDIT ONLY)  
**Firebase Project:** `chainvault-staging`  
**Database ID:** `(default)` (Cloud Firestore, Standard Edition)  
**Authoritative Backend:** `DATABASE_BACKEND=mongodb` (Unchanged, 100% Intact)  
**Security Posture:** Zero Cloud Resources Created, Zero IAM Roles Granted, Zero Keys Generated  

---

## 1. Executive Summary & Audit Scope

Following Phase 4C, where the Cloud Firestore `(default)` database, security rules (`allow read, write: if false;`), and all 5 composite indexes were validated and deployed, Phase 4D performs a comprehensive **readiness audit for backend IAM and authentication**.

In accordance with strict safety directives:
- **No Cloud Mutations:** No service accounts, service-account keys, or IAM role bindings were created.
- **No Backend Switching:** The application's active persistence engine remains strictly `DATABASE_BACKEND=mongodb`.
- **No Credential Exposure:** No keys, tokens, or secret values were generated, exposed, or committed.
- **Authoritative Preservation:** All 6 MongoDB records, evidence binaries, forensic PDF reports, and blockchain state remain 100% untouched.

---

## 2. Firestore Adapter Credential-Loading Inspection

The persistence adapter was audited in [`backend/app/database/firestore.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py):

### 2.1 Configuration Variables
The `FirestoreClient` reads the following environment variables upon instantiation:
- `FIREBASE_PROJECT_ID` (falls back to `GCP_PROJECT`, default `chainvault-staging`)
- `FIRESTORE_DATABASE_ID` (default `(default)`)
- `FIRESTORE_EMULATOR_HOST` (e.g., `127.0.0.1:8080`)
- `GOOGLE_APPLICATION_CREDENTIALS` (optional path to service-account JSON key)
- `REQUIRE_PERSISTENT_STORAGE` (boolean flag enforcing fail-closed behavior)

### 2.2 Three-Tier Credential Resolution Flow
Lines 506–515 of [`firestore.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/app/database/firestore.py#L506-L515) establish a clear three-tier resolution precedence:

```python
if self.emulator_host:
    os.environ["FIRESTORE_EMULATOR_HOST"] = self.emulator_host
    self._client = AsyncClient(project=self.project_id, database=self.database_id)
elif self.credentials_path and os.path.exists(self.credentials_path):
    self._client = AsyncClient.from_service_account_json(self.credentials_path, database=self.database_id)
else:
    self._client = AsyncClient(project=self.project_id, database=self.database_id)
```

1. **Tier 1 — Local Emulator (Highest Precedence):**
   - Triggered when `FIRESTORE_EMULATOR_HOST` is set.
   - Bypasses all Google Cloud IAM authentication and routes gRPC calls directly to the local emulator loopback.
2. **Tier 2 — Explicit Service-Account Key File:**
   - Triggered when `GOOGLE_APPLICATION_CREDENTIALS` is set and the target file physically exists.
   - Loads credentials via `AsyncClient.from_service_account_json()`.
3. **Tier 3 — Application Default Credentials (ADC) Standard Fallback:**
   - Triggered when both `FIRESTORE_EMULATOR_HOST` and `GOOGLE_APPLICATION_CREDENTIALS` are absent.
   - Instantiates `AsyncClient(project=self.project_id, database=self.database_id)`, delegating to Google's standard `google.auth.default()` credential chain:
     1. User credentials created via `gcloud auth application-default login` (`%APPDATA%\gcloud\application_default_credentials.json` on Windows).
     2. GCE / Cloud Run / GKE metadata server (`http://metadata.google.internal`).

### 2.3 Local Workstation ADC Diagnostic Probe
A safe diagnostic probe using `google.auth.default()` was executed in the local environment:
- **Result:** `DefaultCredentialsError: Your default credentials were not found.`
- **Finding:** ADC is not currently initialized on this workstation (expected before running `gcloud auth application-default login`). The adapter code is fully prepared to use ADC seamlessly as soon as the developer logs in.

---

## 3. Minimum IAM Permissions & Least-Privilege Predefined Role

### 3.1 Backend Operation Inventory
The ChainVault backend performs the following data-plane operations against Cloud Firestore across its 8 collections (`cases`, `evidence`, `audit_logs`, `custody_transactions`, `idempotency_records`, `blockchain_checkpoints`, `reports`, `users`):
1. **Document CRUD:** Single-document reads (`get`), writes (`create`, `set`), and deletions (`delete`).
2. **Batch & Multi-Document Operations:** Multi-document queries (`find`), prefix range scans, and batch deletes (`delete_many`).
3. **Atomic Transactions & Lease Locking:** Distributed transactions with optimistic concurrency control (`@async_transactional`), CAS version increments (`fencing_version`), and conditional lease updates.
4. **Aggregation Queries:** Collection counts (`col_ref.count()`).

### 3.2 Granular IAM Permissions Mapping
The specific Google Cloud IAM permissions exercised by these operations are:
- `datastore.databases.get`
- `datastore.databases.runQuery`
- `datastore.databases.runAggregationQuery`
- `datastore.entities.get`
- `datastore.entities.list`
- `datastore.entities.create`
- `datastore.entities.update`
- `datastore.entities.delete`
- `datastore.indexes.list`

### 3.3 Role Evaluation & Recommendation

| Role | Role Name | Least Privilege? | Suitability Analysis |
| :--- | :--- | :---: | :--- |
| **`roles/datastore.user`** | **Cloud Datastore User** | **YES (Recommended)** | **Optimal.** Grants complete data-plane read/write/transaction access to all documents and indexes without any administrative capabilities. Cannot delete databases, modify security rules, alter IAM, or manage billing. |
| `roles/datastore.viewer` | Cloud Datastore Viewer | Inadequate | Read-only. Rejects evidence registration, custody transfers, audit logging, and lease locks. |
| `roles/datastore.owner` | Cloud Datastore Owner | Violates Least Privilege | Grants excessive administrative privileges, including deleting the entire database and managing cloud backups. |
| `roles/editor` | Project Editor | Violates Least Privilege | Grants broad, destructive edit permissions across the entire Google Cloud project. |
| `roles/firebase.admin` | Firebase Admin | Violates Least Privilege | Grants administrative control over Firebase Auth, Storage, Hosting, and Project Settings. |

> [!TIP]
> **Recommendation:** Grant strictly **`roles/datastore.user` (Cloud Datastore User)** on project `chainvault-staging` to the service account or developer identity. Do not grant broader roles.

---

## 4. Application Default Credentials (ADC) vs Long-Lived Service-Account Keys

### 4.1 Security Comparison

| Attribute | Application Default Credentials (ADC) | Long-Lived Service-Account Key File (`.json`) |
| :--- | :--- | :--- |
| **Token Lifetime** | Short-lived OAuth 2.0 access tokens (~1 hour) | Indefinite (valid until manually revoked) |
| **File on Disk** | User refresh token in `%APPDATA%\gcloud\` | RSA Private Key stored directly in project/filesystem |
| **Git Leakage Risk** | **Zero** (never placed in project directory) | **High** (frequent accidental commits to repositories) |
| **Key Rotation** | Handled automatically by Google OAuth | Manual rotation required (operational overhead) |
| **Audit Logging** | Attributed to individual developer identity | Shared service account identity (harder to audit) |
| **Revocation** | Instant via Google Account console / session kill | Requires deleting the key in GCP Console / CLI |

### 4.2 Security Determination
**Application Default Credentials (ADC) CAN and SHOULD be used safely for local developer testing.**  
Creating a long-lived service-account JSON key is unnecessary and discouraged for local development. By using ADC, developers authenticate via their own Google accounts, and no private key file ever touches the project repository.

---

## 5. Environment Setup Playbooks

### 5.1 Playbook A: Windows Developer Setup (Safe ADC Workflow)

This workflow enables a developer on Windows to run local tests against the Cloud Firestore staging database without generating any service-account key files.

#### Step 1: Install Google Cloud SDK (`gcloud` CLI)
If `gcloud` is not already installed:
- Via Windows Package Manager: `winget install Google.CloudSDK`
- Or via the official installer: `https://cloud.google.com/sdk/docs/install#windows`

#### Step 2: Authenticate User Identity for ADC
Run from PowerShell:
```powershell
gcloud auth application-default login
```
*A browser window opens. Log in with the Google account that has access to `chainvault-staging`.*  
*This stores short-lived credentials at `%APPDATA%\gcloud\application_default_credentials.json` outside the repository.*

#### Step 3: Ensure IAM Role is Granted
The Google Cloud project administrator runs (or assigns in Console):
```bash
gcloud projects add-iam-policy-binding chainvault-staging \
    --member="user:developer-email@example.com" \
    --role="roles/datastore.user"
```

#### Step 4: Configure Local `.env` (When Testing Staging Firestore)
```ini
FIREBASE_PROJECT_ID=chainvault-staging
FIRESTORE_DATABASE_ID=(default)
# Ensure FIRESTORE_EMULATOR_HOST is commented out or unset
# Ensure GOOGLE_APPLICATION_CREDENTIALS is commented out or unset
```

---

### 5.2 Playbook B: Future Staging-Runtime Setup (Cloud Deployment)

When deploying the ChainVault backend service to a staging environment (e.g., Google Cloud Run or Render), use the appropriate credential strategy:

#### Scenario 1: Google Cloud Run (Recommended for Zero-Secret Cloud Hosting)
1. Create a dedicated runtime service account:
   ```bash
   gcloud iam service-accounts create chainvault-staging-backend \
       --description="ChainVault Staging Backend Service Account" \
       --display-name="chainvault-staging-backend"
   ```
2. Bind the least-privilege role:
   ```bash
   gcloud projects add-iam-policy-binding chainvault-staging \
       --member="serviceAccount:chainvault-staging-backend@chainvault-staging.iam.gserviceaccount.com" \
       --role="roles/datastore.user"
   ```
3. Deploy to Cloud Run with `--service-account=chainvault-staging-backend@chainvault-staging.iam.gserviceaccount.com`.
4. **Zero Keys Needed:** The Cloud Run metadata server automatically provisions short-lived tokens via ADC.

#### Scenario 2: Render Web Service (Third-Party Cloud Platform)
If hosting on Render:
1. Generate a single dedicated service-account key strictly for staging:
   ```bash
   gcloud iam service-accounts keys create sa-key.json \
       --iam-account=chainvault-staging-backend@chainvault-staging.iam.gserviceaccount.com
   ```
2. In the Render Dashboard, upload `sa-key.json` as a **Render Secret File** mounted at `/etc/secrets/gcp-sa.json`.
3. In Render environment variables, configure:
   ```ini
   ENVIRONMENT=staging
   REQUIRE_PERSISTENT_STORAGE=true
   DATABASE_BACKEND=firestore
   FIREBASE_PROJECT_ID=chainvault-staging
   FIRESTORE_DATABASE_ID=(default)
   GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/gcp-sa.json
   ```
4. Never store `sa-key.json` in Git or local workspace.

---

## 6. Git & Secret Protection Verification

### 6.1 `.gitignore` Hardening
The repository's [`.gitignore`](file:///D:/parjaayi%20project/CHAINVAULT/.gitignore) was inspected and hardened to protect all credential filename patterns:
```gitignore
# Cloud & Service Account Credentials
*.pem
*.key
*service_account*.json
*service-account*.json
*credentials*.json
*firebase-adminsdk*.json
*gcp-key*.json
*sa-key*.json
secrets/
backend/secrets/

# Firebase & Cloud Logs
firebase-debug.log*
firestore-debug.log*
ui-debug.log*
```

### 6.2 Tracking Audit
- A Git index scan verified that **zero** credential files, private keys, or `.env` files are tracked.
- Automated tests in [`backend/tests/test_audit_security.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_audit_security.py) programmatically verify `.gitignore` pattern coverage.

---

## 7. Local Test Results & Authoritative Verification

### 7.1 Test Execution
All relevant local tests were executed cleanly:
```powershell
backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_audit_security.py backend/tests/test_firestore_adapter.py
```
**Result:** **25 passed in 8.12s** (100% PASS)

Key verified assertions:
- `test_gitignore_protects_cloud_credentials`: Confirmed all service-account, Firebase Admin SDK, and key patterns are blocked.
- `test_env_example_database_backend_defaults_to_mongodb`: Confirmed `.env.example` defaults to MongoDB.
- `test_firestore_adapter_credential_loading_precedence`: Confirmed emulator vs explicit key vs ADC resolution logic.
- `test_fail_closed_when_persistent_storage_required`: Confirmed strict fail-closed persistence behavior.
- `test_live_emulator_*` (10 tests): Confirmed CRUD, lease locks, idempotency, and audit hash invariants.

### 7.2 Authoritative Database Parity
A live non-destructive count of MongoDB database `chainvault` verified zero records modified:
- `idempotency_records`: 0
- `audit_logs`: 3
- `cases`: 0
- `evidence`: 2
- `blockchain_checkpoints`: 1
- `reports`: 0
**Total: exactly 6 records, 100% preserved.**

---

## 8. Risks, Blockers & Next Steps

### 8.1 Current Blockers
- **ADC on Local Machine:** `google.auth.default()` fails on this Windows machine because `gcloud auth application-default login` has not yet been executed by the developer. This is expected and non-blocking for local MongoDB development.

### 8.2 Safe Next Steps (Requires User Execution / Approval)
1. **Developer Machine:** Install `gcloud` and run `gcloud auth application-default login` when developer testing against staging Firestore is desired.
2. **GCP Console / IAM:** Grant `roles/datastore.user` to the developer's user identity or the dedicated staging service account on project `chainvault-staging`.
3. **No Automatic Switch:** Keep `DATABASE_BACKEND=mongodb` as the primary operational engine until staging readiness is fully signed off.

---

## 9. Conclusion

**Phase 4D Audit Completed.**  
The backend's Firestore persistence adapter is architecturally ready for Cloud Firestore via Application Default Credentials (ADC) without requiring high-risk static private keys. The least-privilege role is identified as `roles/datastore.user`. All local tests pass, and authoritative MongoDB data remains completely untouched.
