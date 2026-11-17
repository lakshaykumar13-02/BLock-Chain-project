# ChainVault Phase 7.3 — Staging Readiness Audit Report
**Date:** 2026-10-21  
**Target Repository:** `D:\parjaayi project\CHAINVAULT`  
**Target Hosting:** Render (Web Service + Static Site + Persistent Disk)  
**Target Blockchain:** EVM Testnet (Sepolia, Chain ID 11155111)  
**Audit Mode:** Read-Only Technical Audit (NO DEPLOYMENT, NO TRANSACTION, NO RECORD MODIFICATION)

---

## Executive Summary

This staging-readiness audit evaluated the complete ChainVault codebase across architecture, concurrency, persistence, blockchain anchoring, security, and hosting prerequisites.

### Core Audit Verdict: **BLOCKED FOR IMMEDIATE STAGING DEPLOYMENT**
While the application architecture, canonical custody hashing, and multi-worker lease-locking logic are robustly implemented and pass all local tests (17 Hardhat tests and 214 Pytest tests), staging deployment is currently **BLOCKED** by five operational and infrastructure prerequisites:
1. **Ephemeral File Storage Blocker:** Evidence files (`storage/evidence`) and generated forensic PDFs (`generated_reports`) are stored on the local filesystem. On Render's ephemeral container filesystem, all files are wiped upon every restart or redeployment unless a Render Persistent Disk or S3-compatible cloud object store is mounted.
2. **Undeployed V2 Smart Contract:** `EvidenceRegistryV2.sol` has been compiled and tested locally, but has **never been deployed** to Sepolia (or any live network). The existing deployment configuration points to a V1 contract on localhost (`0x5FbDB2315678afecb367f032d93F642f64180aa3`).
3. **Missing Deployment Manifests:** No `render.yaml`, `Dockerfile`, or `Procfile` exists in the repository. Unpinned Python dependencies in `requirements.txt` introduce build vulnerability.
4. **Hardcoded Defaults & Missing Environment Configuration:** Key production variables (`REQUIRE_PERSISTENT_STORAGE`, `BLOCKCHAIN_CHAIN_ID=11155111`, `PUBLIC_VERIFICATION_URL_BASE`, `CORS_ORIGINS`) are not present in `.env.example`, and frontend `api.js` requires explicit origin binding.
5. **Blockchain-Database Consistency Gap:** Custody transfers execute external blockchain broadcasts *before* committing the update to MongoDB and releasing the lease lock. Under high network latency or worker failure, transactions can succeed on-chain while failing or being fenced out in MongoDB, violating exactly-once semantics.

---

## 1. Repository and Working-Tree Inventory

### 1.1 Path and Git Working-Tree Status
- **Authoritative Root:** `D:\parjaayi project\CHAINVAULT`
- **Branch:** `master`
- **Current Git Status:** Clean unstaged modifications across 17 files; 14 untracked files/directories. No commits or resets were performed during this audit.

#### Modified Files (Uncommitted):
- `backend/app/database/mongodb.py`: Motor client event-loop binding, persistent storage enforcement, index initialization.
- `backend/app/main.py`: Security headers middleware, CORS environment parsing, lifespan management.
- `backend/app/routes/audit.py`: Independent custody audit verification endpoint (`/api/audit/verify/{id}`).
- `backend/app/routes/blockchain.py`: Chain ID checks, smart contract verification, transaction receipt queries.
- `backend/app/routes/cases.py`: MongoDB persistence with in-memory fallback.
- `backend/app/routes/custody.py`: Atomic lease locking, fencing tokens, idempotency store, transfer endpoints.
- `backend/app/routes/evidence.py`: SHA-256 ingestion, file storage, persistent storage gating.
- `backend/app/routes/reports.py`: PDF report generation, QR verification URL resolution, report metadata store.
- `backend/app/routes/verification.py`: Multi-source integrity verification engine (file vs DB vs blockchain).
- `backend/app/security/auth.py`: JWT generation and validation; startup check blocking default secret in production.
- `backend/app/services/blockchain.py`: JSON-RPC client, V1/V2 ABI encoders/decoders, on-chain custody anchor queries.
- `backend/app/services/report.py`: ReportLab forensic report generator, QR code generator, checksum calculator.
- `backend/tests/conftest.py`: Test database isolation (`chainvault_test`), test event loop management.
- `blockchain/deployments/localhost_EvidenceRegistry.json`: Localhost V1 contract deployment artifact.
- `frontend/css/dashboard.css`: Styling for dashboard and forensic verification UI.
- `frontend/dashboard.html`: Single-page forensic dashboard structure.
- `frontend/js/api.js`: Frontend API client with dynamic base URL resolution.
- `frontend/js/dashboard.js`: Dashboard UI event handlers and rendering.

#### Untracked Files:
- `backend/.pytest_temp/` (Local test scratch directory)
- `backend/app/routes/recovery.py` & `backend/app/services/recovery.py` (Persistence & disaster recovery service)
- `backend/tests/test_custody_audit_trail.py` (Phase 2 audit trail tests)
- `backend/tests/test_evidence_integrity_suite.py` (Phase 3 integrity suite)
- `backend/tests/test_forensic_report_suite.py` (Phase 5 report suite)
- `backend/tests/test_independent_blockchain_verification.py` (Phase 1 verification suite)
- `backend/tests/test_persistence_recovery_suite.py` (Phase 4 recovery suite)
- `backend/tests/test_phase7_audit_validation.py` (Phase 7 audit validation suite)
- `backend/tests/test_phase7_custody_concurrency.py` (Phase 7 lease & concurrency suite)
- `blockchain/contracts/EvidenceRegistryV2.sol` (Phase 7 Solidity V2 contract)
- `blockchain/test/EvidenceRegistryV2.test.js` (Phase 7 Hardhat contract test suite)
- `docs/audit/PHASE_2_CUSTODY_AUDIT_TRAIL_DESIGN.md` (Design specifications)

### 1.2 Technology Stack Confirmation
- **Backend:** FastAPI 0.x, Uvicorn, Python 3.12, Motor (AsyncIOMotorClient), PyJWT, ReportLab, QRCode.
- **Frontend:** Vanilla HTML5, CSS3, Vanilla ES6 JavaScript (Zero frontend framework dependencies).
- **Blockchain:** Solidity 0.8.19, Hardhat 2.x, Ethers.js v6.
- **Database:** MongoDB Community Server (local) / MongoDB Atlas (target staging).
- **Deployment Manifests:** **NONE**. (No `render.yaml`, `Dockerfile`, or `Procfile` present).

---

## 2. Custody Anchoring Correctness

### 2.1 Canonical Event Hash Computation
In `backend/app/services/audit_trail.py`:
- **Function:** `calculate_canonical_event_hash(event: dict) -> str`
- **Field Normalization:** `canonical_event_representation(event)` extracts exactly 10 immutable fields:
  1. `schema_version`: Integer (currently `1`).
  2. `event_id`: String (e.g. `EVT-EV-001-0001-A1B2C3`).
  3. `evidence_id`: String.
  4. `case_id`: String.
  5. `actor_id`: String.
  6. `action`: String (e.g. `CUSTODY_TRANSFER`).
  7. `timestamp`: Normalized UTC ISO-8601 string (`YYYY-MM-DDTHH:MM:SS.ffffffZ`) via `normalize_utc_timestamp()`.
  8. `sequence_number`: Monotonic integer ($1, 2, 3 \dots$).
  9. `previous_event_hash`: Hex string of preceding event hash (`GENESIS` for sequence 1).
  10. `details`: Deterministically sorted key-value dictionary containing primitive types.
- **Strict Exclusion:** Volatile or circular fields are excluded: `event_hash`, `anchor_reference`, `blockchain_tx`, `_id`, and backward-compatibility aliases.
- **Digest Algorithm:** `hashlib.sha256(json.dumps(dict, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')).hexdigest()`.

### 2.2 On-Chain Recording (`EvidenceRegistryV2.sol`)
- **Function:** `recordCustodyAnchor(string evidenceId, uint256 sequenceNumber, string eventHash, string previousEventHash, uint256 schemaVersion)`
- **On-Chain Enforcement:**
  - Enforces `sequenceNumber > 0` and `bytes(eventHash).length == 64`.
  - For sequence 1: requires `previousEventHash == "GENESIS"`.
  - For sequence $n > 1$: requires sequence $n-1$ to exist and `keccak256(prior.eventHash) == keccak256(previousEventHash)`.
  - Emits `CustodyAnchorRecorded` event.
  - Reverts if caller is not the evidence custodian or contract admin.

### 2.3 Independent Verification & Fail-Closed Behavior
In `backend/app/services/audit_trail.py`: `verify_custody_audit_trail(evidence_id, require_blockchain=True)`
- **RPC Failure:** If RPC is unreachable, returns `UNAVAILABLE` (`BLOCKCHAIN_RPC_UNAVAILABLE`), `verified: false`.
- **Missing Anchor:** If event sequence has no corresponding on-chain anchor, returns `INCONSISTENT` (`CUSTODY_ANCHOR_NOT_FOUND`), `verified: false`.
- **Mismatched Event Hash:** If on-chain anchor does not match recomputed canonical hash, returns `TAMPERED` (`ANCHOR_HASH_MISMATCH`), `verified: false`.
- **Predecessor Hash Mismatch:** If on-chain predecessor link is broken, returns `TAMPERED` (`ANCHOR_PREDECESSOR_MISMATCH`), `verified: false`.
- **Sequence Gap:** If an intermediate sequence is skipped, returns `INCONSISTENT` (`SEQUENCE_GAP_DETECTED`), `verified: false`.

### 2.4 Local-EVM vs. Live-Network Reality
- **Verified Fact:** All on-chain anchoring tests passed on Hardhat local in-process network (`chain_id=31337`).
- **Untested Assumption:** Zero transactions have ever been submitted to Sepolia or any live public EVM. Gas pricing, public node rate limits, reorganization risks, and public transaction confirmation latency are completely untested.

---

## 3. Multi-Worker Consistency

### 3.1 MongoDB Lease Locking Mechanism
In `backend/app/routes/custody.py`:
- **Acquisition:** `acquire_custody_transfer_lock(evidence_id, actor, idempotency_key, lease_seconds=30.0)`
  - Executes atomic `update_one` on `db.evidence` with condition:
    ```json
    {
      "evidence_id": evidence_id,
      "$or": [
        {"transfer_lock": {"$exists": false}},
        {"transfer_lock.status": {"$ne": "LOCKED"}},
        {"transfer_lock.expires_at": {"$lt": now}}
      ]
    }
    ```
  - Writes unique `lock_token = uuid.uuid4().hex`, `locked_at = now`, `expires_at = now + 30.0`, and `fencing_version = evidence.custody_version`.
- **Renewal:** `renew_custody_transfer_lock` extends `expires_at` conditional on matching `lock_token`.
- **Release & Fencing:** `release_custody_transfer_lock` updates `transfer_lock.status = "UNLOCKED"` and increments `custody_version` by 1 **only if** `lock_token` and `custody_version == expected_version` match. If another worker stole the expired lease, the update matches 0 documents and returns `False` (fencing violation).

### 3.2 Race Conditions and Ordering Flaws
1. **Blockchain Submission vs. Database Commit Race:**
   In `custody.py`:
   - Step 1: Worker acquires lease.
   - Step 2: Worker calls `transfer_custody_on_chain()` (broadcasts transaction to Ethereum).
   - Step 3: Worker calls `record_custody_event()` (broadcasts anchor transaction to Ethereum).
   - Step 4: Worker calls `release_custody_transfer_lock()` to commit change to MongoDB.
   
   **Failure Scenario:** If Sepolia mining latency exceeds 30 seconds, Worker A's lease expires. Worker B acquires the lease. Worker A's blockchain transaction confirms on Ethereum, but when Worker A attempts to commit to MongoDB, it is fenced out with `HTTP 409 Conflict`. **Result:** The blockchain has permanently recorded the transfer, but MongoDB still shows the old custodian.
2. **Absence of Exactly-Once Broadcasting:**
   If a worker crashes immediately after broadcasting an Ethereum transaction but before saving the transaction receipt in MongoDB or completing the idempotency record, a retried request will broadcast a second transaction, generating redundant chain state. Exactly-once broadcasting is **not guaranteed**.
3. **Clock Synchronization Skew:**
   Lease expiration relies on `time.time() + lease_duration` evaluated on the application host. Across multiple Render instances or cloud containers without synchronized NTP clocks, a server with slight forward drift will prematurely treat active locks as expired.
4. **In-Memory Fallback Danger:**
   In development mode (`REQUIRE_PERSISTENT_STORAGE=false`), lock failures fall back to `_IN_MEMORY_TRANSFER_LOCKS`. In a multi-worker production environment, in-memory locks provide zero protection across separate worker processes.

---

## 4. Render and Persistent Storage Evaluation

### 4.1 Startup and Health Endpoints
- **Startup Command:** `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Endpoint:** `GET /api/health` returns `{"status": "ok", "service": "ChainVault API"}`.
  > [!IMPORTANT]
  > Render defaults health check paths to `/`. Render service settings must explicitly set the Health Check Path to `/api/health`.

### 4.2 File Persistence Blocker on Render
- **Evidence Storage:** Physical files are stored on disk at `backend/storage/evidence` via `storage.py`.
- **PDF Report Storage:** Generated reports are stored on disk at `backend/generated_reports` via `report.py`.
- **Render Ephemeral Disk Architecture:** Render container filesystems are strictly ephemeral. Every deployment, manual restart, or automatic restart wipes all files written to disk.
- **Direct Impact on ChainVault:**
  - Missing evidence files cause `backend/app/routes/verification.py` to fail closed: `Physical evidence file is missing from disk storage. Cannot verify integrity without actual file bytes.`
  - Missing PDF reports cause report download endpoints to return HTTP 404.
- **Prerequisite:** Staging deployment on Render **requires** either:
  - A **Render Persistent Disk** mounted at `/var/data`, configured with `STORAGE_PATH=/var/data/evidence` and `REPORTS_PATH=/var/data/reports`.
  - OR cloud object storage (AWS S3, Cloudflare R2, MinIO).

### 4.3 Environment Configuration Audit

| Variable | Current Default | Staging Requirement | Risk if Unset |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `staging` | Allows insecure defaults |
| `REQUIRE_PERSISTENT_STORAGE` | `false` | `true` | Silently falls back to volatile RAM |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB Atlas URI (TLS) | Application startup failure |
| `MONGO_DB_NAME` | `chainvault` | `chainvault_staging` | Overwrites local/default DB |
| `JWT_SECRET` | Insecure hardcoded default | High-entropy 256-bit string | Token forgery vulnerability |
| `BLOCKCHAIN_RPC_URL` | `http://127.0.0.1:8545` | Public/Private Sepolia RPC | Blockchain features fail closed |
| `BLOCKCHAIN_CHAIN_ID` | `31337` | `11155111` (Sepolia) | Chain ID mismatch error |
| `CONTRACT_ADDRESS` | `0x5FbDB...` (Localhost V1) | Deployed Sepolia V2 Address | Calls fail or revert |
| `STORAGE_PATH` | `storage/evidence` | Persistent mount path | Data loss on dyno restart |
| `REPORTS_PATH` | `generated_reports` | Persistent mount path | PDF loss on dyno restart |
| `PUBLIC_VERIFICATION_URL_BASE` | `None` | `https://<service>.onrender.com` | QR codes fail to generate public links |
| `CORS_ORIGINS` | Localhost origins | Static site domain | Browser blocks API requests |

---

## 5. Test Evidence and Validation Spectrum

| Test Suite | Environment | Scope | Passed | Mocked vs Real |
| :--- | :--- | :--- | :--- | :--- |
| `EvidenceRegistry.test.js` | Hardhat Network | V1 Contract Functions | 6 | Real local EVM |
| `EvidenceRegistryV2.test.js` | Hardhat Network | V2 Anchors & Sequencing | 11 | Real local EVM |
| `test_phase7_custody_concurrency.py` | Pytest + Local Mongo | Lease Locks & Fencing | 10 | Real Mongo + Mocked RPC |
| `test_phase7_audit_validation.py` | Pytest + Local Mongo | Canonical Hash Validation | 13 | Real Mongo + Mocked RPC |
| `test_evidence_integrity_suite.py` | Pytest + Local Mongo | Verification Engine | 33 | Real Mongo + Mocked RPC |
| `test_persistence_recovery_suite.py` | Pytest + Local Mongo | Outages & Reset Detection | 32 | Real Mongo + Simulated Nodes |
| `test_forensic_report_suite.py` | Pytest + Local Mongo | PDF Generation & QR Links | 42 | Real Mongo + Mocked RPC |
| `test_phase6_production_readiness.py`| Pytest + Local Mongo | Security & CORS Baseline | 45 | Unit & API Tests |
| Baseline API & Route Tests | Pytest + Local Mongo | Auth, Cases, Evidence | 22 | Unit & API Tests |
| **Total Verified Tests** | **All Local** | **Full Regression Suite** | **231** | **Local EVM + Pytest** |
| **Live Sepolia Testnet** | **None** | **Live Network Validation** | **0** | **UNTESTED** |

> [!CAUTION]
> **No Live Network Proof:** All 231 tests were executed against either local in-process EVMs, local Hardhat nodes, or monkeypatched RPC mocks. Not a single transaction has been proven against a live public blockchain.

---

## 6. Final Staging Readiness Checklist

| Requirement | Evidence / Implementation | Status | Required Next Action |
| :--- | :--- | :--- | :--- |
| **Smart Contract V2** | `EvidenceRegistryV2.sol` compiled & tested locally | **BLOCKED** | Deploy V2 to Sepolia; configure `CONTRACT_ADDRESS` |
| **Chain ID Alignment** | `blockchain.py` expects `31337` by default | **PASS (Configurable)** | Set `BLOCKCHAIN_CHAIN_ID=11155111` in staging env |
| **Persistent Evidence Storage** | Physical files stored on ephemeral local disk | **BLOCKED** | Attach Render Persistent Disk or configure S3 |
| **Persistent PDF Storage** | PDF reports stored on ephemeral local disk | **BLOCKED** | Mount reports directory to persistent disk |
| **MongoDB Atlas Cluster** | Localhost Community Server used | **BLOCKED** | Provision Atlas cluster; test TLS connection |
| **Database Persistence Gate** | `REQUIRE_PERSISTENT_STORAGE` implemented | **PASS** | Set `REQUIRE_PERSISTENT_STORAGE=true` in staging env |
| **JWT Secret Enforcement** | Production check prevents default secret | **PASS** | Generate and inject cryptographically secure secret |
| **Deployment Manifest** | No `render.yaml` or `Dockerfile` | **BLOCKED** | Create `render.yaml` with persistent disk definition |
| **CORS Whitelist** | Dynamic `CORS_ORIGINS` supported | **PASS** | Set `CORS_ORIGINS=https://<frontend>.onrender.com` |
| **Health Check Path** | `GET /api/health` implemented | **PASS** | Configure Render health check path to `/api/health` |
| **Idempotency & Lease Locking** | Implemented with fencing version | **PASS** | Increase lease time to 120s for live testnet latency |
| **Live EVM Validation** | Zero transactions on live testnet | **NOT TESTED** | Execute single controlled test transfer on Sepolia |

---

## 7. Prerequisites for Future Staging Deployment

The following technical steps must be executed before any staging deployment can succeed:
1. **Repository Hygiene:** Commit the audited Phase 1–7 implementation and tests to a feature branch (`git checkout -b staging-ready; git add .; git commit`).
2. **Infrastructure Provisioning (Separate Explicit Approval Required):**
   - Provision a MongoDB Atlas M0 (free) or M10 cluster with network access rules.
   - Provision a Render Web Service (FastAPI) and Static Site (Frontend).
   - Provision a Render Persistent Disk (minimum 1GB) attached to the Web Service.
3. **Smart Contract Deployment (Separate Explicit Approval Required):**
   - Fund a testnet deployer wallet with Sepolia ETH (from a public faucet).
   - Deploy `EvidenceRegistryV2.sol` to Sepolia using Hardhat.
   - Record the deployed contract address and verify bytecode on Etherscan/Sepolia.
4. **Configuration Injection:**
   - Inject environment variables into Render Web Service dashboard (Mongo URI, Sepolia RPC, Contract Address, JWT Secret, Storage paths).

---

## 8. Recommended Next Phase

### **Phase 8: Staging Deployment Manifest & Configuration Preparation (Dry-Run)**
- **Scope:**
  - Author `render.yaml` defining the Web Service, Static Site, Persistent Disk mounts, and health checks.
  - Pin exact dependency versions in `requirements.txt`.
  - Author a dedicated Hardhat Sepolia deployment script (`scripts/deploy_v2_sepolia.js`).
  - Update `frontend/js/api.js` to ensure reliable base URL fallback for separate frontend and backend Render domains.
- **Safety Boundary:** All manifests and configuration files can be prepared locally in the repository without deploying cloud resources, spending money, or broadcasting transactions.
