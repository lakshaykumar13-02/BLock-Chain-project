# ChainVault — Configuration, Environment & Data Integrity Audit (Phase D)

**Audit Date:** 2026-10-13  
**Audit Author:** Antigravity Master Project Audit Agent  
**Authoritative Workspace:** `D:\parjaayi project\CHAINVAULT`  
**Current Git Branch:** `master`  

---

## 1. Executive Summary & Configuration Baseline

This audit inspects environment configuration, credential security, path resolution, database isolation, blockchain parameters, and data integrity safeguards across all tiers of the ChainVault platform.

---

## 2. Secrets & Credential Exclusion Audit

1. **Hardcoded Secrets Inspection:**
   - Evaluated all Python modules in `backend/app/`. No production secrets, plaintext passwords, or private keys are hard-coded.
   - In `backend/app/routes/auth.py`, user credentials in `DEMO_USERS` store salted bcrypt password hashes (`$2b$12$...`) generated at runtime import via `hash_password()`.
   - In `backend/app/security/auth.py`, `JWT_SECRET` defaults to a safe fallback placeholder (`"chainvault_default_secret_key_change_in_production"`), overridable via `.env`.
   - In `blockchain/`, Hardhat scripts (`deploy.js`, `verify_standalone_integration.js`, and tests) strictly obtain test signer accounts through `hre.ethers.getSigners()`, avoiding hard-coded Ethereum private keys.

2. **`.env.example` Template Verification:**
   - File inspected: `D:\parjaayi project\CHAINVAULT\.env.example`.
   - Verified that all entries contain safe documentation placeholders:
     - `MONGO_URI=mongodb://localhost:27017`
     - `MONGO_DB_NAME=chainvault`
     - `JWT_SECRET=your_super_secret_key_change_in_production`
     - `JWT_EXPIRE_MINUTES=30`
     - `BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545`
     - `CONTRACT_ADDRESS=` (blank placeholder)
     - `STORAGE_PATH=storage/evidence`
   - Verified test `test_audit_security.py::test_env_example_contains_all_required_keys` passes.

3. **`.gitignore` Boundary Enforcement:**
   - File inspected: `D:\parjaayi project\CHAINVAULT\.gitignore`.
   - Excludes:
     - Local environment files: `.env`, `.env.local`
     - Python artifacts: `__pycache__/`, `*.pyc`, `venv/`, `.pytest_cache/`
     - Node artifacts: `node_modules/`, `blockchain/artifacts/`, `blockchain/cache/`
     - Dynamic data stores: `backend/storage/evidence/*`, `backend/generated_reports/*`
   - Verified test `test_audit_security.py::test_gitignore_protects_evidence_and_reports` passes.

---

## 3. Network Ports, Configuration Precedence & Cross-Tier Agreement

| Parameter | Frontend Expectation | Backend Active Config | Blockchain Node Config | Status | Agreement Verified |
|---|---|---|---|---|---|
| **API Base URL** | `http://localhost:8000/api` (`api.js`) | `http://127.0.0.1:8000/api` (`main.py`) | N/A | Aligned | Yes (Port 8000) |
| **Frontend Web Port** | Port 5500 (`login.html`, `dashboard.html`) | Allowed origin in CORS (`origins` in `main.py`) | N/A | Aligned | Yes (Port 5500 in CORS) |
| **Blockchain RPC URL** | N/A | `http://127.0.0.1:8545` (`services/blockchain.py`) | `http://127.0.0.1:8545/` (`hardhat node`) | Aligned | Yes (Port 8545) |
| **Network Chain ID** | Displayed in dashboard as `31337` | Expected `31337` | Hardhat local chain ID `31337` | Aligned | Yes (31337) |
| **Contract Address** | Displayed from API status | `0x5FbDB2315678afecb367f032d93F642f64180aa3` | Deployed address in `deployments/` | Aligned | Yes (`0x5FbDB...`) |
| **MongoDB Socket** | N/A | `mongodb://localhost:27017` (`mongodb.py`) | Windows Service on Port 27017 | Aligned | Yes (Port 27017) |
| **Application DB** | N/A | `chainvault` (Production/Development default) | N/A | Aligned | Default target |
| **Test Database** | N/A | `chainvault_test` (Enforced by `conftest.py`) | N/A | Aligned | Isolated target |

---

## 4. Path References & Workspace Reconciliation

### Workspace Identity Reconciled
- **Documented Path vs Active Path:**
  - Older documentation references `C:\ChainVault` as the default project path.
  - The actual authoritative workspace is `D:\parjaayi project\CHAINVAULT`.
  - Resolution: The master runbook (`docs/demo/DEMO_RUNBOOK.md`) and checkpoint policy (`docs/CHECKPOINT_CREATION_TIMING_POLICY.md`) have been updated to acknowledge `D:\parjaayi project\CHAINVAULT`.
  - All relative module imports (`Path(__file__).resolve().parent.parent.parent`) dynamically anchor relative paths to the actual active workspace root, guaranteeing zero breakage regardless of drive letter.

### Physical File Storage Paths
- `STORAGE_PATH`: Resolves to `backend/storage/evidence/`. Directory is created automatically if absent.
- `REPORTS_PATH`: Resolves to `backend/generated_reports/`. Directory is created automatically if absent.
- Both paths are strictly protected against directory traversal (`..`, `/`, `\`) with canonical path prefix checks (`str(file_path).startswith(str(target_dir))`).

---

## 5. Data Integrity & Test Isolation Safeguards

1. **Automated Test Database Safeguard:**
   - In `backend/app/database/mongodb.py`:
     ```python
     def safeguard_test_database(self, operation: str = "destructive"):
         if self.db_name != "chainvault_test":
             raise PermissionError(
                 f"Destructive operation '{operation}' rejected: active database is '{self.db_name}', "
                 f"not the designated test database 'chainvault_test'."
             )
     ```
   - Automated tests in `test_data_integrity.py` prove:
     - Any drop operation against `chainvault` raises `PermissionError` (PASS).
     - Drop operations against `chainvault_test` are permitted during test teardown (PASS).

2. **In-Memory Store vs MongoDB Persistence:**
   - **Finding:** FastAPI route controllers (`cases.py`, `evidence.py`, `custody.py`, `reports.py`) manage active session data in module-level in-memory dictionaries.
   - **Verification:** The MongoDB Community Server Windows Service is running and live Motor CRUD operations pass in test suites. However, route-level mutations do not execute asynchronous Motor write operations.
   - **Assessment:** This architecture provides extremely fast, deterministic test execution and resilient offline operation. Evaluators must be explicitly informed that in-memory state resets upon Uvicorn server restarts.

3. **Evidence Immutability Safeguard:**
   - The application does not register any `DELETE` or `PUT` route for digital evidence.
   - Any HTTP `DELETE /api/evidence/{id}` request is rejected with `405 Method Not Allowed`.
   - Verified by `test_security_baseline.py::test_no_evidence_delete_endpoint`.

4. **Forensic Digest Verification:**
   - Generating a forensic report (`POST /api/reports/generate`) independently computes the SHA-256 hash of the generated PDF bytes and saves it in `REPORTS_REGISTRY`.
   - Downloading the report (`GET /api/reports/download/{filename}`) streams the identical bytes.
   - Verified in `test_pdf_report_layout.py::test_pdf_report_api_endpoint_end_to_end`: `hashlib.sha256(down_bytes).hexdigest() == reported_hash`.
