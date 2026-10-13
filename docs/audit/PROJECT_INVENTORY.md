# ChainVault — Project Inventory & State Baseline (Phase A)

**Audit Date:** 2026-10-13  
**Audit Author:** Antigravity Master Project Audit Agent  
**Authoritative Workspace:** `D:\parjaayi project\CHAINVAULT`  
**Current Git Branch:** `master`  
**Latest Commit Hash:** `af13aa91c84d2cb4b8bd0c2c8a2a1825e7676545` (`af13aa9`)  
**Previous Checkpoint:** `Checkpoint: Phase 13.3 — Documentation Audit & Final Validation Complete` (`cc3374f`)  

---

## 1. Executive Summary & Authoritative Workspace Boundary

ChainVault is a digital forensics academic prototype platform developed for a BCA Cybersecurity & Forensics project. Its core mission is **Blockchain-Based Digital Evidence Integrity & Chain-of-Custody Tracking**.

### Workspace & Repository Boundary Confirmation
- **Authoritative Root:** `D:\parjaayi project\CHAINVAULT` is verified as the active Git repository (`On branch master`).
- **External Path Clarification:** References in older documentation to `C:\ChainVault` represent an alternate or historical location. All commands, code, tests, and artifacts in this audit strictly target `D:\parjaayi project\CHAINVAULT`.
- **Working Tree State:** Not clean upon initial inspection. Uncommitted working changes exist in:
  - `backend/app/services/report.py` (enhanced ReportLab Platypus layout with `NumberedCanvas`)
  - `frontend/dashboard.html` (comprehensive 5-view navigation, modals, and event bindings)
  - `frontend/css/dashboard.css` (view styling, responsive tables, modal stylesheets)
  - `frontend/js/api.js` (complete API client methods covering all backend routes)
  - `frontend/js/auth.js` (login handling, role session storage, token forwarding)
  - `frontend/js/dashboard.js` (complete view management, table rendering, action handlers)
  - `frontend/login.html` (script version query-string updates)
  - `backend/tests/test_pdf_report_layout.py` (untracked test suite with 7 layout-verification tests)
- **User Change Protection:** Uncommitted changes have been carefully inspected. They represent advanced UI and PDF layout enhancements. No files were discarded or overwritten.

---

## 2. Directory Structure & Asset Inventory

```
D:\parjaayi project\CHAINVAULT\
├── .env.example                               # Safe environment variable template with placeholders
├── .gitignore                                 # Git exclusion rules for venv, node_modules, reports, evidence
├── README.md                                  # High-level project documentation
├── backend/                                   # Python FastAPI backend service
│   ├── pytest.ini                             # Pytest configuration (pythonpath = ., testpaths = tests)
│   ├── requirements.txt                       # Python dependency manifest
│   ├── venv/                                  # Isolated Python 3.13.14 virtual environment
│   ├── storage/evidence/                      # Physical digital evidence directory (gitignored)
│   ├── generated_reports/                     # Generated PDF forensic reports directory (gitignored)
│   ├── app/                                   # Core application package
│   │   ├── main.py                            # FastAPI entry point, CORS, security headers, routers
│   │   ├── database/
│   │   │   └── mongodb.py                     # Motor AsyncIOMotorClient wrapper & test safeguards
│   │   ├── models/                            # Pydantic schemas and models
│   │   ├── routes/                            # Route controllers
│   │   │   ├── audit.py                       # Audit trail query endpoints
│   │   │   ├── auth.py                        # Authentication, bcrypt login, logout, bootstrap
│   │   │   ├── blockchain.py                  # On-chain anchoring, health, reconciliation
│   │   │   ├── cases.py                       # Case CRUD and admin soft-deletion
│   │   │   ├── custody.py                     # Custody handover and history tracking
│   │   │   ├── evidence.py                    # Evidence ingestion, SHA-256 calculation, download
│   │   │   ├── reports.py                     # QR code streaming, PDF generation, report download
│   │   │   └── verification.py                # Tripartite (File vs Mongo vs Blockchain) verification
│   │   ├── security/                          # Security modules
│   │   │   ├── auth.py                        # JWT generation and validation (HS256)
│   │   │   ├── password.py                    # Bcrypt password hashing and verification
│   │   │   └── permissions.py                 # 4-role RBAC enums and dependency injector
│   │   ├── services/                          # Business logic services
│   │   │   ├── blockchain.py                  # Blockchain service, RPC health, transaction records
│   │   │   ├── hashing.py                     # SHA-256 calculation for bytes, strings, and files
│   │   │   ├── report.py                      # ReportLab Platypus PDF generation & QR generator
│   │   │   └── storage.py                     # Safe filesystem file persistence & traversal defense
│   │   └── utils/                             # Utility helpers
│   └── tests/                                 # Automated Pytest test suites (102 tests)
│       ├── conftest.py                        # Global autouse fixture enforcing chainvault_test DB
│       ├── integration/                       # Tier-to-tier integration tests
│       │   ├── test_evidence_lifecycle.py     # 11-step end-to-end synthetic evidence lifecycle
│       │   ├── test_fastapi_blockchain.py     # RPC configuration and standalone node health
│       │   ├── test_fastapi_mongodb.py        # Live MongoDB Community Server CRUD & indexing
│       │   └── test_frontend_fastapi.py       # Frontend URL alignment & zero secret leakage
│       ├── test_api_contract_security.py      # RBAC, missing/invalid token, immutability
│       ├── test_audit_security.py             # Password hashing, gitignore secrets exclusion
│       ├── test_cors.py                       # Authorized CORS origins verification
│       ├── test_data_integrity.py             # 13 tests: isolation, tamper detection, missing files
│       ├── test_database_config.py            # MongoDB defaults, collections, and live ping
│       ├── test_evidence_hashing.py           # SHA-256 cryptographic verification
│       ├── test_feature_coverage.py           # Endpoint existence & route mapping
│       ├── test_health.py                     # Health API and 404 handler
│       ├── test_pdf_report_layout.py          # 7 tests: PDF magic bytes, wrapping, pagination, XML
│       ├── test_rbac_regression.py            # 4-role permission definitions & mutation block
│       ├── test_security_baseline.py          # Method Not Allowed on DELETE, traversal defense
│       └── test_security_regression.py        # 22 tests: auth attacks, input traversal, headers
├── blockchain/                                # Ethereum / Hardhat layer
│   ├── hardhat.config.js                      # Hardhat EVM config (Solidity 0.8.19)
│   ├── package.json                           # Node.js dependencies (@nomicfoundation/hardhat-toolbox)
│   ├── package-lock.json                      # Pinned Node dependencies
│   ├── contracts/
│   │   └── EvidenceRegistry.sol               # Solidity smart contract (register, transfer, verify)
│   ├── deployments/
│   │   └── localhost_EvidenceRegistry.json    # Deployed contract ABI, bytecode, and deployment info
│   ├── scripts/
│   │   ├── deploy.js                          # Standalone deployment script for localhost
│   │   └── verify_standalone_integration.js   # 5-step standalone node verification script
│   └── test/
│       └── EvidenceRegistry.test.js           # 6 Chai/Mocha smart contract unit tests
├── frontend/                                  # Vanilla HTML5 / CSS3 / JavaScript frontend
│   ├── index.html                             # Scaffolding redirect
│   ├── login.html                             # Forensic authentication portal
│   ├── dashboard.html                         # Unified 5-view forensic workstation dashboard
│   ├── css/
│   │   ├── auth.css                           # Login view styling
│   │   ├── dashboard.css                      # Dashboard grid, panels, modals, badges, toast banner
│   │   ├── responsive.css                     # Mobile and tablet breakpoints
│   │   └── style.css                          # Base design system tokens and typography
│   └── js/
│       ├── api.js                             # Client-side API integration library (20 functions)
│       ├── auth.js                            # Session persistence, login execution, role routing
│       └── dashboard.js                       # View routing, live stats, table binding, modal triggers
└── docs/                                      # Master documentation
    ├── CHANGELOG.md                           # Checkpoint registry and milestone logs
    ├── CHECKPOINT_CREATION_TIMING_POLICY.md   # Policy for checkpoint creation triggers
    ├── CHECKPOINT_RETENTION_CLEANUP_POLICY.md # Policy for checkpoint retention and backup pruning
    ├── CHECKPOINT_VERIFICATION_RECOVERY_TESTING_POLICY.md # Policy for recovery verification
    ├── CONFIGURATION_REFERENCE.md             # Parameter dictionary and environment settings
    ├── ENVIRONMENT_CONFIGURATION_POLICY.md    # Environment isolation rules
    ├── EXACT_ROLLBACK_POLICY.md               # Step-by-step rollback procedures
    ├── Master_Specification.md                # 21-section master specification numbering
    ├── PHASE_TRANSITION_APPROVAL_POLICY.md    # Approval gates between project phases
    ├── RECOVERY_LOG.md                        # Documented recovery tests
    ├── ROLLBACK_LOG.md                        # SEV-1 / SEV-2 incident log (currently 0 incidents)
    ├── api/
    │   ├── API_CONTRACT_AUDIT.md              # 4-layer contract alignment report
    │   └── ENDPOINT_INVENTORY.md              # Complete route catalog
    ├── demo/
    │   ├── DEMO_RUNBOOK.md                    # Operational SOP, service startup order, health checks
    │   ├── DEMO_SCRIPT.md                     # Presentation script for viva/evaluator examination
    │   ├── EVALUATOR_QA.md                    # Technical responses to 11 evaluator questions
    │   ├── KNOWN_LIMITATIONS.md               # prototype constraints and forensic boundaries
    │   ├── PHASE_13_2_DEMO_REPORT.md          # 14-step workflow demonstration report
    │   └── PREFLIGHT_REPORT.md                # Toolchain and port preflight report
    └── testing/
        ├── BLOCKER_INVENTORY.md               # Historical blocker log (BLK-01 to BLK-09 resolved)
        ├── BUG_LOG.md                         # Historical bug tracking (BUG-01 to BUG-11 resolved)
        ├── COVERAGE_MATRIX.md                 # 13 requirement traceability matrix
        ├── DATA_INTEGRITY_AUDIT.md            # Data isolation and tamper detection audit
        ├── INTEGRATION_TEST_REPORT.md         # Component integration test results
        ├── REGRESSION_TEST_REPORT.md          # Regression test audit results
        ├── SECURITY_TEST_REPORT.md            # Security controls and RBAC test results
        ├── TEST_CASES.md                      # Detailed test case definitions
        ├── TEST_EVIDENCE_TRACEABILITY.md      # Command-to-result traceability log
        └── TEST_REPORT.md                     # Consolidated testing report
```

---

## 3. Technology Stack Verification & Adherence

| Layer | Locked Specification | Actual Implementation Found | Status | Notes / Discrepancies |
|---|---|---|---|---|
| **Frontend Structure** | HTML5, CSS3, Vanilla JS | `dashboard.html`, `login.html`, Vanilla JS | Confirmed | Zero React, Vue, Angular, Vite, or TailwindCSS. Vanilla CSS and JS only. |
| **Backend Framework** | Python FastAPI with Uvicorn | FastAPI `0.115+`, Uvicorn | Confirmed | Mounted under `/api` in `app/main.py`. |
| **Database** | MongoDB Community Server (local) | MongoDB Community Server running (Windows Service, Port 27017) | Confirmed | Driver: Motor `AsyncIOMotorClient`. TCP port 27017 verified active. |
| **Blockchain EVM** | Hardhat Local EVM | Hardhat `2.29.1` | Confirmed | Node.js v22.20.0, Chain ID 31337, Port 8545. |
| **Smart Contract** | Solidity 0.8.19 | `EvidenceRegistry.sol` (Solidity 0.8.19) | Confirmed | Contract deployed at `0x5FbDB2315678afecb367f032d93F642f64180aa3`. |
| **Client Web3** | Node.js / ethers.js v6 | `ethers` v6 in Hardhat scripts | Confirmed | In-process testing & standalone scripts use ethers.js v6. |
| **Cryptographic Hashing** | SHA-256 via Python `hashlib` | `backend/app/services/hashing.py` | Confirmed | True bitstream SHA-256 calculation for raw bytes and physical files. |
| **Storage Layer** | Local filesystem | `backend/storage/evidence/` | Confirmed | Files stored off-chain; raw bytes never committed on blockchain. |
| **Authentication** | JWT HS256 + bcrypt | `pyjwt` (HS256) + `bcrypt` | Confirmed | Bcrypt password hashing; Bearer JWT authorization. |
| **Reporting** | ReportLab PDF | ReportLab `SimpleDocTemplate` + `NumberedCanvas` | Confirmed | Dynamic PDF with SHA-256 digest, auto-wrapping tables, repeating headers. |
| **QR Code** | Python `qrcode` | `qrcode` PNG streaming | Confirmed | Direct verification URL streamed as `image/png`. |

---

## 4. API Endpoints & Route Mapping

The application defines 21 FastAPI routes and 6 Solidity smart contract functions:

| Method | Endpoint Path | Source File | Required Role | Summary & Purpose |
|---|---|---|---|---|
| `GET` | `/api/health` | `main.py` | Public | System liveness probe; returns `{"status": "ok"}` |
| `POST` | `/api/auth/login` | `routes/auth.py` | Public | Authenticates credentials with bcrypt; issues signed JWT |
| `POST` | `/api/auth/logout` | `routes/auth.py` | Authenticated | Terminates active user session |
| `GET` | `/api/auth/bootstrap` | `routes/auth.py` | Public | Probes bootstrap admin initialization status without exposing credentials |
| `POST` | `/api/cases` | `routes/cases.py` | Admin, Investigator | Creates a new forensic case record |
| `GET` | `/api/cases` | `routes/cases.py` | Authenticated | Lists all active cases (filters out soft-deleted records) |
| `GET` | `/api/cases/{case_id}` | `routes/cases.py` | Authenticated | Retrieves specific case metadata |
| `DELETE` | `/api/cases/{case_id}` | `routes/cases.py` | Admin Only | Soft-deletes case record by marking `is_deleted=True` |
| `POST` | `/api/evidence/upload` | `routes/evidence.py` | Admin, Investigator | Ingests file, validates size (<50MB) and filename, saves to disk, computes SHA-256 |
| `GET` | `/api/evidence` | `routes/evidence.py` | Authenticated | Lists all ingested evidence records |
| `GET` | `/api/evidence/{evidence_id}` | `routes/evidence.py` | Authenticated | Retrieves specific evidence metadata |
| `GET` | `/api/evidence/download/{filename:path}` | `routes/evidence.py` | Authenticated | Downloads physical evidence file with path traversal defense |
| `POST` | `/api/blockchain/register` | `routes/blockchain.py` | Admin, Investigator | Anchors evidence ID and SHA-256 hash to the local Ethereum ledger |
| `GET` | `/api/blockchain/status` | `routes/blockchain.py` | Public | Returns local blockchain node status (`online` / `offline`) and RPC URL |
| `GET` | `/api/blockchain/evidence/{evidence_id}` | `routes/blockchain.py` | Authenticated | Reads on-chain evidence record directly from ledger state |
| `POST` | `/api/blockchain/reconcile/{evidence_id}` | `routes/blockchain.py` | Admin, Investigator | Synchronizes pending transaction status without redundant on-chain writes |
| `POST` | `/api/custody/transfer` | `routes/custody.py` | Admin, Investigator | Transferees custody, appends to audit log, and records event on-chain |
| `GET` | `/api/custody/history/{evidence_id}` | `routes/custody.py` | Authenticated | Retrieves custody handover log history |
| `POST` | `/api/verification/verify` | `routes/verification.py` | Public / All | Tripartite verification: recomputes disk hash, compares to Mongo and Blockchain |
| `GET` | `/api/reports/qr/{evidence_id}` | `routes/reports.py` | Public | Generates and streams PNG QR verification badge |
| `POST` | `/api/reports/generate` | `routes/reports.py` | Admin, Inv, Analyst | Compiles formal forensic PDF report with case, evidence, and custody audit tables |
| `GET` | `/api/reports/download/{filename}` | `routes/reports.py` | Authenticated | Downloads compiled PDF report with path traversal validation |
| `GET` | `/api/reports/history/{case_id}` | `routes/reports.py` | Authenticated | Retrieves history of all compiled reports for a case |
| `GET` | `/api/audit/logs/{evidence_id}` | `routes/audit.py` | Authenticated | Retrieves chronological audit events for evidence item |
| `GET` | `/api/audit/all` | `routes/audit.py` | Admin, Investigator | Retrieves all audit events across the platform |

---

## 5. Persistence, State Management & Architectural Discrepancy

A critical architectural finding of this inventory:

1. **MongoDB Connection:**
   - `MongoDBClient` in `backend/app/database/mongodb.py` is configured and connects cleanly to `mongodb://localhost:27017` via Motor on startup.
   - Live MongoDB integration tests (`test_fastapi_mongodb.py` and `test_database_config.py`) pass 100% against the active Windows Service `MongoDB`.
2. **In-Memory Store Usage in Routes:**
   - The route controllers (`cases.py`, `evidence.py`, `custody.py`, `reports.py`, `services/blockchain.py`) currently utilize module-level in-memory dictionaries (`CASES_STORE`, `EVIDENCE_STORE`, `AUDIT_LOGS_STORE`, `REPORTS_REGISTRY`, `CHAIN_EVIDENCE_STORE`) to hold live session state.
   - **Architectural Consequence:** State persisted during a server process lifetime survives all route operations, but is volatile if the Python process restarts unless backed by MongoDB collections.
   - This in-memory architecture was documented in Phase 13.3 (`KNOWN_LIMITATIONS.md`) as an intentional resilient prototype design allowing test execution both with and without an active MongoDB daemon.

---

## 6. Live Service & Port Inventory

| Service | Intended Port | Active Host Status | Diagnostic Evidence |
|---|---|---|---|
| **MongoDB Community Server** | `27017` | **LISTENING** | `TCP 127.0.0.1:27017 LISTENING` (PID 7676, Windows Service `MongoDB`) |
| **Hardhat JSON-RPC Node** | `8545` | **NOT RUNNING** | `netstat -ano \| findstr 8545` returned no listening socket |
| **FastAPI Backend (Uvicorn)** | `8000` | **NOT RUNNING** | No process bound to port 8000 |
| **Frontend HTTP Server** | `5500` | **NOT RUNNING** | No process bound to port 5500 |

*Operational Note:* MongoDB is running as a durable Windows service. The remaining three local services (Hardhat node, FastAPI, Frontend HTTP) are standard on-demand terminal processes launched according to `docs/demo/DEMO_RUNBOOK.md`.

---

## 7. Baseline Test Execution Results

Executing the full automated test suites on the current codebase:

1. **Hardhat Smart Contract Suite (`npx hardhat test`):**
   - **Result:** `6 passing (11s)`
   - **Status:** **PASS (100%)**
   - **Coverage:** Deployment admin initialization, isolated signers, evidence hash registration, custody handover with event emission, on-chain hash verification, duplicate evidence rejection.

2. **Pytest Backend Suite (`pytest -v --basetemp=./.pytest_temp`):**
   - **Total Tests Collected:** 102 items
   - **Passing Tests:** 101 tests passed
   - **Failing Tests:** 1 test failed (`test_fastapi_blockchain.py::test_blockchain_rpc_reachability_detection`)
   - **Root Cause of Failure:** Standalone Hardhat node on port 8545 is not currently running; test asserted `check_blockchain_health() is True`.
   - **All 7 PDF Layout Tests:** **PASSED** (`test_pdf_report_layout.py`)
   - **All 31 Security Regression Tests:** **PASSED** (`test_security_regression.py`)
   - **All 13 Data Integrity Tests:** **PASSED** (`test_data_integrity.py`)
   - **All 11 Lifecycle Steps:** **PASSED** (`test_evidence_lifecycle.py`)

---

## 8. Classification of Features

- **Confirmed Implemented & Verified:**
  - Bcrypt password hashing and JWT authentication.
  - 4-Role RBAC enforcement on all mutation endpoints (ADMIN, INVESTIGATOR, ANALYST, VIEWER).
  - Case creation, listing, retrieval, and Admin-only soft deletion.
  - Evidence upload, 50MB ceiling, character sanitization, disk storage, and SHA-256 calculation.
  - Solidity smart contract logic (`registerEvidence`, `transferCustody`, `verifyEvidence`).
  - Tripartite integrity verification recomputing physical disk file hash and pairwise comparisons.
  - Tamper detection returning `verified: False`, `tampered: True`.
  - Dynamic QR verification badge generation streamed as PNG.
  - Tamper-evident forensic PDF compilation with `NumberedCanvas` (Page X of Y), table auto-wrapping, and repeating headers.
  - Defensive security headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`).
  - Path traversal protections on both evidence and report downloads.
  - Safe database test isolation (`chainvault_test` safeguard).
- **Configuration-Dependent:**
  - Standalone Hardhat node connectivity (requires running `npx hardhat node` on port 8545).
  - Durable MongoDB storage vs. in-memory session store.
- **Planned / Prototype Scope Boundaries (from `KNOWN_LIMITATIONS.md`):**
  - 50 MB single-evidence upload limit.
  - QR code URL resolves to localhost (`http://localhost:8000/...`).
  - Ephemeral Hardhat state resets upon node termination.
  - Local loopback network binding.
