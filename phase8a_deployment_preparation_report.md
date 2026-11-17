# ChainVault Phase 8A — Deployment Preparation Report (Dry Run Only)

**Date:** 2026-10-21  
**Authoritative Repository:** `D:\parjaayi project\CHAINVAULT`  
**Execution Mode:** Dry Run & Local Preparation Only (NO CLOUD CREATION, NO TRANSACTION BROADCAST, NO DATABASE MIGRATION)  

---

## Executive Summary

Phase 8A successfully prepared ChainVault's deployment manifests, runtime configurations, dependency pins, storage resolution, and deployment checklists locally in the repository. All changes strictly adhere to the read-only and non-destructive mandates.

### Core Deliverables Prepared:
1. **Render Deployment Manifest (`render.yaml`):** Infrastructure-as-code specification defining a standard Python FastAPI Web Service (`chainvault-api`) with an attached 10GB persistent disk mounted at `/var/data`, and a companion static frontend site (`chainvault-frontend`).
2. **Pinned Python Dependencies (`backend/requirements.txt`):** Pinned exact versions matching the active, verified local virtual environment (e.g., `fastapi==0.142.2`, `uvicorn==0.54.0`, `motor==3.7.1`, `reportlab==5.0.1`).
3. **Comprehensive Staging Template (`.env.example`):** Fully documented placeholders covering Atlas connection strings, 256-bit JWT secret generation, Sepolia JSON-RPC parameters, persistent disk paths, and CORS origins without leaking any secrets.
4. **Cross-Domain Frontend API Resolution (`frontend/js/api.js`):** Multi-tier base URL resolution supporting `window.__CHAINVAULT_API_URL__`, `localStorage.getItem('chainvault_api_url')`, localhost development fallback, and same-origin reverse proxy without hardcoding any invented domain.
5. **Persistent Disk Path Resolution:** Updated `storage.py`, `report.py`, and `recovery.py` to seamlessly handle both relative paths and absolute persistent disk paths (`/var/data/evidence`, `/var/data/reports`).
6. **Dry-Run Guarded Sepolia Deployment Script (`blockchain/scripts/deploy_v2_sepolia.js`):** Script that compiles `EvidenceRegistryV2`, checks configuration, refuses to broadcast without explicit `DEPLOY_BROADCAST=true`, and never exposes private keys.
7. **Deployment Checklist (`docs/deployment/STAGING_DEPLOYMENT_CHECKLIST.md`):** Step-by-step operational runbook detailing pre-deployment authorizations, manual Atlas/Render setups, smoke tests, and rollback procedures.

---

## 1. Render Deployment Specification (`render.yaml`)

The blueprint specification was created at `D:\parjaayi project\CHAINVAULT\render.yaml`:

### 1.1 Backend Web Service (`chainvault-api`)
- **Runtime:** Python 3.12 (`PYTHON_VERSION=3.12.0`)
- **Plan:** `standard` (Required to support persistent disk attachments)
- **Root Directory:** `backend`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/api/health`
- **Persistent Disk:**
  - Name: `chainvault-storage`
  - Mount Path: `/var/data`
  - Size: 10 GB
- **Environment Variables:**
  - `ENVIRONMENT`: `staging`
  - `REQUIRE_PERSISTENT_STORAGE`: `"true"` (Forces fail-closed behavior if database disconnects)
  - `MONGO_URI`: `sync: false` (Secured in dashboard)
  - `MONGO_DB_NAME`: `chainvault_staging`
  - `JWT_SECRET`: `generateValue: true` (Render auto-generates 256-bit random key)
  - `JWT_EXPIRE_MINUTES`: `"60"`
  - `BLOCKCHAIN_RPC_URL`: `sync: false` (Sepolia RPC provider)
  - `BLOCKCHAIN_CHAIN_ID`: `"11155111"` (Ethereum Sepolia Testnet)
  - `CONTRACT_ADDRESS`: `sync: false` (Target `EvidenceRegistryV2` address)
  - `STORAGE_PATH`: `/var/data/evidence`
  - `REPORTS_PATH`: `/var/data/reports`
  - `PUBLIC_VERIFICATION_URL_BASE`: `sync: false`
  - `CORS_ORIGINS`: `sync: false`
  - `ALLOW_LOCAL_QR_LINKS`: `"false"`

### 1.2 Frontend Static Site (`chainvault-frontend`)
- **Runtime:** `static`
- **Root Directory:** `frontend`
- **Build Command:** `""` (Pure HTML5/CSS/Vanilla JS, zero compilation required)
- **Static Publish Path:** `.`
- **Defensive Headers:** Injects `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy: strict-origin-when-cross-origin`.

---

## 2. Pinned Python Dependencies (`backend/requirements.txt`)

Direct dependencies were pinned to the exact working versions verified in `.\venv\Scripts\pip freeze`:

| Package | Previous (Unpinned) | Pinned Working Version | Purpose |
| :--- | :--- | :--- | :--- |
| `fastapi` | unpinned | `fastapi==0.142.2` | Core ASGI web framework |
| `uvicorn` | unpinned | `uvicorn==0.54.0` | ASGI application server |
| `pydantic` | unpinned | `pydantic==2.13.5` | Data validation and schemas |
| `motor` | unpinned | `motor==3.7.1` | Async MongoDB Motor driver |
| `python-dotenv` | unpinned | `python-dotenv==1.2.4`| Environment variable loader |
| `bcrypt` | unpinned | `bcrypt==5.0.0` | Password hashing |
| `PyJWT` | unpinned | `PyJWT==2.15.1` | HMAC-SHA256 JWT signing |
| `reportlab` | unpinned | `reportlab==5.0.1` | PDF forensic report generation |
| `qrcode` | unpinned | `qrcode==8.2` | Tamper-evident QR code rendering |
| `python-multipart` | unpinned | `python-multipart==0.0.32`| File upload parsing |
| `httpx` | unpinned | `httpx==0.28.1` | Test client & async HTTP requests |
| `pytest` | unpinned | `pytest==9.1.1` | Test runner framework |

---

## 3. Staging Configuration Template (`.env.example`)

The `.env.example` file was expanded from 8 sparse lines into a production-grade configuration template documenting:
- Strict persistent storage enforcement (`REQUIRE_PERSISTENT_STORAGE=true`).
- MongoDB Atlas connection string structure (`mongodb+srv://...`).
- 256-bit cryptographically secure JWT secrets.
- Sepolia JSON-RPC parameters (`BLOCKCHAIN_CHAIN_ID=11155111`).
- Mount paths for evidence (`/var/data/evidence`) and reports (`/var/data/reports`).
- Public verification URL resolution (`PUBLIC_VERIFICATION_URL_BASE`).
- Whitelisted CORS origins for cross-domain browser requests.

---

## 4. Cross-Domain Frontend API Configuration (`frontend/js/api.js`)

To support separate hosting of the frontend and backend on Render without hardcoding invented domains, `frontend/js/api.js` was enhanced with `getResolvedApiBaseUrl()`:
1. **Window-Level Injection:** Checks `window.__CHAINVAULT_API_URL__` (can be injected via deployment script or index.html).
2. **Browser Storage Override:** Checks `localStorage.getItem('chainvault_api_url')` or `sessionStorage.getItem('chainvault_api_url')`. Enables administrators or users to point the static frontend to any backend URL at runtime.
3. **Localhost Fallback:** Automatically defaults to `http://localhost:8000/api` when accessed on `localhost` or `127.0.0.1`.
4. **Same-Origin Fallback:** Defaults to `${window.location.origin}/api` if deployed under a unified reverse proxy.
5. **Config Helper:** Exposes `window.setConfiguredApiBaseUrl(url)` on the global window object.

---

## 5. Persistent Storage Path Architecture

On Render, the container filesystem is ephemeral, while persistent disks are mounted at an absolute path (e.g. `/var/data`). The application codebase was verified and adapted:
- **`backend/app/services/storage.py`:** `get_storage_path()` checks `Path(STORAGE_DIR).is_absolute()`. If absolute, it resolves directly to `/var/data/evidence` and creates parent directories without prepending the repository root.
- **`backend/app/services/report.py`:** `get_reports_dir()` similarly resolves absolute paths for `/var/data/reports`.
- **`backend/app/services/recovery.py`:** Updated storage accessibility checks and orphaned file scans to use `get_storage_path()` rather than assuming relative working directory execution.

---

## 6. Hardhat Sepolia Deployment Script & Dry-Run Safeguard

### 6.1 Safe Script: `blockchain/scripts/deploy_v2_sepolia.js`
- Compiles and verifies the `EvidenceRegistryV2` contract artifact.
- Validates that `SEPOLIA_RPC_URL` and `SEPOLIA_PRIVATE_KEY` are provided when targeting Sepolia.
- **Dry-Run Enforcement:** Unless `DEPLOY_BROADCAST=true` is explicitly set in the execution environment, the script terminates immediately with status 0, printing:
  ```text
  SAFETY GUARD ACTIVE: DEPLOY_BROADCAST is not set to 'true'.
  Dry-run validation successful. No transactions were broadcast.
  ```
- **Secret Redaction:** Never prints or logs the private key.

### 6.2 Hardhat Network Configuration (`blockchain/hardhat.config.js`)
- Conditionally adds the `sepolia` network only if `SEPOLIA_RPC_URL` and a valid 64-character `SEPOLIA_PRIVATE_KEY` exist in the environment.
- Does not affect local in-process testing or require external dependencies.

---

## 7. Validation Results (Safe Local Execution Only)

### 7.1 Hardhat Contract Tests
- **Command:** `npx hardhat test` (Cwd: `blockchain/`)
- **Result:**
  ```text
  EvidenceRegistry Smart Contract & Blockchain Suite
    ✔ 6 passing (2s)
  EvidenceRegistryV2 Smart Contract — Local EVM Suite
    ✔ 11 passing (1s)

  17 passing (3s)
  ```

### 7.2 Hardhat Deployment Script Dry-Run Validation
- **Command:** `npx hardhat run scripts/deploy_v2_sepolia.js` (Cwd: `blockchain/`)
- **Result:**
  ```text
  ===============================================
  ChainVault V2 Deployment Script (Dry-Run Guarded)
  Target Network: hardhat
  ===============================================
  Loading contract artifact for EvidenceRegistryV2...
  EvidenceRegistryV2 factory compiled and loaded successfully.
  -----------------------------------------------
  SAFETY GUARD ACTIVE: DEPLOY_BROADCAST is not set to 'true'.
  Dry-run validation successful. No transactions were broadcast.
  -----------------------------------------------
  ```

### 7.3 Backend Regression & Configuration Tests
- **Basic Health & CORS Tests:**
  - **Command:** `pytest tests/test_health.py tests/test_cors.py tests/test_database_config.py`
  - **Result:** `6 passed in 3.33s`
- **Persistence & Recovery Tests:**
  - **Command:** `pytest tests/test_persistence_recovery_suite.py`
  - **Result:** `19 passed in 14.37s`
- **Phase 7 Concurrency & Audit Validation Tests:**
  - **Command:** `pytest tests/test_phase7_custody_concurrency.py tests/test_phase7_audit_validation.py`
  - **Result:** `23 passed in 45.69s`

---

## 8. Inventory of Modified and New Files

### Modified Files:
1. `backend/requirements.txt`: Direct dependencies pinned to verified working versions.
2. `.env.example`: Comprehensive documented staging configuration template.
3. `frontend/js/api.js`: Enhanced dynamic API base URL resolution.
4. `backend/app/services/storage.py`: Absolute path support for persistent disk mounts.
5. `backend/app/services/report.py`: Absolute path support for persistent report directories.
6. `backend/app/services/recovery.py`: Standardized storage directory checks.
7. `blockchain/hardhat.config.js`: Safe conditional Sepolia network configuration.

### New Files:
1. `render.yaml`: Render Blueprint infrastructure manifest.
2. `blockchain/scripts/deploy_v2_sepolia.js`: Dry-run guarded Sepolia deployment script.
3. `docs/deployment/STAGING_DEPLOYMENT_CHECKLIST.md`: Step-by-step deployment runbook.
4. `phase8a_deployment_preparation_report.md`: Phase 8A technical audit and preparation report.

---

## 9. Remaining Blockers before Live Staging Deployment

The following actions require external cloud provisioning and separate explicit user authorization before any staging launch can occur:
1. **Render Cloud Provisioning:** Creating the Blueprint, Web Service, Static Site, and Persistent Disk on Render.
2. **MongoDB Atlas Cluster:** Provisioning an M0/M10 Atlas cluster and obtaining the TLS connection URI.
3. **Sepolia Deployer Funding:** Generating a dedicated testnet wallet and obtaining testnet ETH from a public faucet.
4. **On-Chain V2 Contract Deployment:** Broadcasting `EvidenceRegistryV2.sol` to Sepolia testnet to obtain a live contract address.
5. **Git Remote Push:** Pushing the local commits and manifests to a remote Git repository for Render integration.

---

## 10. Explicit Confirmation of Safety Compliance

- **Cloud Deployment:** Zero services or cloud resources deployed to Render.
- **Transactions:** Zero blockchain transactions broadcast; zero testnet or mainnet funds spent.
- **Smart Contracts:** Zero contracts deployed to live networks.
- **Database:** Zero records created, deleted, modified, or migrated in MongoDB. The 4 residual checkpoints remain untouched.
- **Git State:** Zero destructive Git commands, resets, or discards executed.
