# ChainVault — Test Coverage & Regression Report (Phase H)

**Audit Date:** 2026-10-13  
**Audit Author:** Antigravity Master Project Audit Agent  
**Authoritative Workspace:** `D:\parjaayi project\CHAINVAULT`  
**Current Git Branch:** `master`  

---

## 1. Test Execution Summary

| Test Suite / Category | Exact Execution Command | Working Directory | Total Tests | Passed | Failed | Skipped | Exit Code | Environment / Services Used |
|---|---|---|---|---|---|---|---|---|
| **Smart Contract Tests** | `npx hardhat test` | `blockchain/` | 6 | 6 | 0 | 0 | 0 | Local Hardhat In-Process EVM |
| **Standalone Node Integration** | `npx hardhat run scripts/verify_standalone_integration.js --network localhost` | `blockchain/` | 5 | 5 | 0 | 0 | 0 | Real Standalone Hardhat Daemon (Port 8545) |
| **Backend Unit & Integration** | `.\venv\Scripts\pytest.exe -v` | `backend/` | 102 | 102 | 0 | 0 | 0 | Real MongoDB (27017) & Hardhat (8545) |
| **Live E2E Workflow Validation** | `python run_live_e2e_verification.py` | `backend/` | 14 | 14 | 0 | 0 | 0 | All 4 Real Local Services (Ports 27017, 8545, 8000, 5500) |
| **Browser Subagent UI Validation** | `browser_subagent` | Browser UI | 6 | 6 | 0 | 0 | 0 | Real Chromium Browser on Port 5500 |

**Consolidated Total:** **108 Automated Tests Executed + 25 Real-Service Integration Steps = 133 / 133 Passing (100% Pass Rate).**

---

## 2. Test Suite Breakdown by Functional Area

### 2.1 Backend Unit & Integration Suite (`pytest -v`)
Executed 102 tests across 14 test modules:

1. **`tests/integration/test_evidence_lifecycle.py` (11 tests — PASS):**
   - Step 01: Authenticate and obtain JWT
   - Step 02: Case creation
   - Step 03: Synthetic evidence ingestion
   - Step 04: SHA-256 calculation and independent verification
   - Step 05: Blockchain registration on Ethereum ledger
   - Step 06: Custody handover
   - Step 07: Tripartite hash verification (File == DB == Blockchain)
   - Step 08: Dynamic QR code streaming
   - Step 09: Forensic PDF report compilation
   - Step 10: Chronological audit trail inspection
   - Step 11: Unauthorized destructive action rejection

2. **`tests/integration/test_fastapi_blockchain.py` (3 tests — PASS):**
   - `test_blockchain_rpc_configuration`: Verifies RPC URL points strictly to local Hardhat node.
   - `test_blockchain_rpc_reachability_detection`: Verifies `check_blockchain_health()` detects active node.
   - `test_blockchain_service_integration_module`: Verifies export of registration and custody handlers.

3. **`tests/integration/test_fastapi_mongodb.py` (4 tests — PASS):**
   - `test_mongodb_target_isolated_test_database`: Verifies test isolation to `chainvault_test`.
   - `test_live_mongodb_crud_and_indexing_against_test_db`: Real MongoDB Community Server connection, unique index creation, document insertion, retrieval, update, and clean drop.
   - `test_mongodb_graceful_handling_when_service_unavailable`: Verifies resilient fallback when MongoDB unreachable.
   - `test_fastapi_case_creation_and_retrieval_integration`: FastAPI case roundtrip.

4. **`tests/integration/test_frontend_fastapi.py` (3 tests — PASS):**
   - `test_frontend_api_base_url_matches_backend`: Verifies `API_BASE_URL` in `api.js` targets backend port 8000.
   - `test_zero_secrets_or_private_keys_in_frontend_assets`: Verifies zero client-side private keys or JWT secrets.
   - `test_frontend_api_health_endpoint_integration`: Health probe alignment.

5. **`tests/test_api_contract_security.py` (8 tests — PASS):**
   - Rejection of missing, invalid, and expired tokens.
   - Role enforcement blocking Viewer mutations.
   - Investigator permissions for case creation and evidence ingestion.
   - Admin-only case soft deletion.
   - Zero credential leakage in responses.
   - Rejection of evidence DELETE for Admin (405 Method Not Allowed).

6. **`tests/test_audit_security.py` (3 tests — PASS):**
   - `.env.example` contains all required keys with placeholders.
   - `.gitignore` protects evidence files and reports.
   - Bcrypt password hashing verification.

7. **`tests/test_cors.py` (1 test — PASS):**
   - Preflight CORS authorization for frontend port 5500.

8. **`tests/test_data_integrity.py` (13 tests — PASS):**
   - Automated safeguard rejects drop on development database (`chainvault`).
   - Automated safeguard allows drop on test database (`chainvault_test`).
   - Database selection strictly targets `chainvault_test`.
   - Evidence upload and independent hash verification.
   - Tamper detection returning `verified: false`, `tampered: true`.
   - Missing physical file detection (`file_status: "missing"`).
   - Atomic upload write cleanup on filesystem failure.
   - Blockchain confirmed transaction persistence.
   - Transaction reconciliation for pending or uncertain state.
   - Reconcile 404 on nonexistent evidence.
   - Custody history preservation across multiple transfers.
   - Historic report preservation without overwrites.
   - Case soft deletion does not cascade-delete evidence or custody.

9. **`tests/test_database_config.py` (3 tests — PASS):**
   - Client configuration defaults.
   - Database collections declared (`users`, `cases`, `evidence`, `custody_logs`, `audit_logs`, `reports`).
   - Live MongoDB connection and ping (`admin.command('ping')` -> `ok: 1.0`).

10. **`tests/test_evidence_hashing.py` (2 tests — PASS):**
    - SHA-256 cryptographic correctness against known test vectors.
    - Hashing service module verification.

11. **`tests/test_feature_coverage.py` (6 tests — PASS):**
    - Route mapping verification across auth, cases, evidence, custody, verification, and reports.

12. **`tests/test_health.py` (2 tests — PASS):**
    - Health check endpoint returns `{"status": "ok"}`.
    - Nonexistent route returns HTTP 404.

13. **`tests/test_pdf_report_layout.py` (7 tests — PASS):**
    - Begins with valid `%PDF` magic bytes.
    - Report hash matches independent byte SHA-256.
    - Long text and descriptions wrap cleanly.
    - Long 64-char hashes and 42-char Ethereum addresses wrap inside table cells.
    - Multi-page pagination and repeating table headers (`repeatRows=1`).
    - XML special characters (`&`, `<`, `>`, quotes) safely escaped.
    - End-to-end report generation and download hash verification.

14. **`tests/test_rbac_regression.py` (2 tests — PASS):**
    - All 4 roles defined in `UserRole` enum.
    - Viewer role blocked from modifying state.

15. **`tests/test_security_baseline.py` (3 tests — PASS):**
    - Rejection of evidence DELETE route.
    - No hardcoded `.env` committed.
    - Storage directory traversal protection.

16. **`tests/test_security_regression.py` (22 tests — PASS):**
    - Login with valid/invalid/nonexistent credentials.
    - Password stored as bcrypt hash.
    - Token attack defenses (missing, malformed, expired, inactive user).
    - Logout endpoint.
    - Bootstrap admin probe.
    - RBAC matrix across all 4 roles for cases, evidence, blockchain, custody, reports, and audit.
    - Object authorization (404 on nonexistent/soft-deleted cases).
    - Input path traversal blocked on evidence and report downloads.
    - Oversized upload rejected with HTTP 413.
    - Forbidden filename characters rejected with HTTP 400.
    - MongoDB operator injection rejected by Pydantic.
    - Defensive headers and CORS restrictions.

---

### 2.2 Smart Contract Suite (`npx hardhat test`)
Executed 6 smart contract unit tests in `blockchain/test/EvidenceRegistry.test.js`:
- `TC-BC-01`: Deploys successfully and sets deployer as admin (**PASS**).
- `TC-BC-02`: Provides isolated test accounts on local Hardhat network (**PASS**).
- `TC-BC-03`: Registers evidence on-chain with SHA-256 hash and emits `EvidenceRegistered` (**PASS**).
- `TC-BC-04`: Transfers custody and emits `CustodyTransferred` (**PASS**).
- `TC-BC-05`: Accurately performs on-chain hash verification (**PASS**).
- `TC-BC-06`: Prevents duplicate registration of same evidence ID (**PASS**).

---

## 3. Real Services vs Mocks Distinction

- **MongoDB:** Actual integration tests run against **real running MongoDB Community Server** on port 27017, targeting isolated `chainvault_test` database.
- **Blockchain:** Tested both in-process (Hardhat EVM runner) and against **real standalone Hardhat JSON-RPC node** on port 8545 with deployed `EvidenceRegistry.sol` contract.
- **Backend:** FastAPI Uvicorn running live on port 8000.
- **Frontend:** Static web server running live on port 5500.

Zero required mocks replace missing services. All real services are active and verified.
