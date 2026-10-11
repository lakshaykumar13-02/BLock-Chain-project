# ChainVault — Test Cases Specification

This document details all test cases defined for Phase 12 validation in accordance with the **ChainVault Test Execution Plan** and **Coverage Matrix** (`docs/testing/COVERAGE_MATRIX.md`).

---

## Group A: Backend and Database

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-BACK-01 | Health Check Endpoint | `/api/health` | Automated (`pytest`) | Returns HTTP 200 with `status: "ok"` | **Passed** |
| TC-BACK-02 | Unmapped Route 404 Handling | `/api/nonexistent` | Automated (`pytest`) | Returns HTTP 404 Not Found | **Passed** |
| TC-DB-01 | MongoDB Client Config Defaults | `MongoDBClient` | Automated (`pytest`) | Client uri and database names correctly defaulted | **Passed** |
| TC-DB-02 | Database Collections Declared | `MongoDBClient` | Automated (`pytest`) | Users, cases, evidence, custody, audit, reports declared | **Passed** |
| TC-DB-03 | Live MongoDB Test Connection | `chainvault_test` | Automated (`pytest`) | Connects to isolated test DB and pings admin | **Blocked** (Service offline - BUG-03) |
| TC-BACK-04 | User Authentication & JWT Login | `/api/auth/login` | Automated (`pytest`) | Valid credentials return JWT; invalid return 401 | **Blocked** (Route unmapped stub) |
| TC-BACK-05 | Case Creation & Metadata | `/api/cases` | Automated (`pytest`) | Valid payload persists case; returns 201 | **Blocked** (Route unmapped stub) |
| TC-BACK-06 | Case Soft Deletion & Query Filter | `/api/cases/{id}` | Automated (`pytest`) | Deleted case marked inactive, excluded from normal queries | **Blocked** (Route unmapped stub) |
| TC-BACK-07 | Role-Based Access Control (RBAC) | Secure endpoints | Automated (`pytest`) | Unauthorized roles receive HTTP 403 Forbidden | **Blocked** (Security stub) |

---

## Group B: Evidence Management & Cryptography

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-EVID-01 | Confirmation of No Delete Endpoint | `/api/evidence/{id}` | Automated (`pytest`) | HTTP DELETE returns 404 (No delete endpoint exists) | **Passed** |
| TC-EVID-04 | Storage Directory Traversal Defense | `/api/evidence/download/..` | Automated (`pytest`) | Traversals rejected with 404 / 400 | **Passed** |
| TC-EVID-05 | SHA-256 Cryptographic Correctness | `hashlib.sha256` | Automated (`pytest`) | Computes exact 64-char hex digest on test vectors | **Passed** |
| TC-EVID-06 | Hashing Service Module Exports | `services/hashing.py` | Automated (`pytest`) | Module exposes `calculate_hash` function | **Blocked** (Service is stub) |
| TC-EVID-02 | Evidence Upload & Storage | `/api/evidence/upload` | Automated (`pytest`) | File accepted, SHA-256 calculated & stored in DB | **Blocked** (Route unmapped stub) |
| TC-EVID-03 | Duplicate Hash Handling | `/api/evidence/upload` | Automated (`pytest`) | Identical hash detected and flagged/handled | **Blocked** (Route unmapped stub) |

---

## Group C: Blockchain Integration

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-BC-01 | Contract Deployer Admin Verification | `EvidenceRegistry.sol` | Hardhat (`test`) | Deployer address matches `admin` state variable | **Passed** |
| TC-BC-02 | Local Network Test Accounts | Hardhat Signers | Hardhat (`test`) | Multiple isolated accounts available for testing | **Passed** |
| TC-BC-03 | Contract Register Function Check | `EvidenceRegistry.sol` | Hardhat (`test`) | Audits presence of `registerEvidence` function | **Passed (Gap Confirmed)** |
| TC-BC-04 | Contract Transfer Function Check | `EvidenceRegistry.sol` | Hardhat (`test`) | Audits presence of `transferCustody` function | **Passed (Gap Confirmed)** |
| TC-BC-05 | Contract Verify Function Check | `EvidenceRegistry.sol` | Hardhat (`test`) | Audits presence of `verifyEvidence` function | **Passed (Gap Confirmed)** |
| TC-BC-06 | Duplicate Evidence Registration Reversion| `EvidenceRegistry.sol` | Hardhat (`test`) | Contract reverts on re-registering existing evidence ID | **Blocked** (Contract is skeleton) |
| TC-BC-07 | Zero Private Key Leakage | Backend & Frontend | Static audit | No private keys present in DB or client bundles | **Passed** |

---

## Group D: Chain of Custody

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-CUST-01 | Custody Transfer Execution | `/api/custody/transfer` | Automated (`pytest`) | Transfers custody to valid officer after on-chain verification | **Blocked** (Route unmapped stub) |
| TC-CUST-02 | Unauthorized Transfer Rejection | `/api/custody/transfer` | Automated (`pytest`) | Non-custodian transfer attempts return HTTP 403 | **Blocked** (Route unmapped stub) |
| TC-CUST-03 | Immutable Custody Audit Trail | MongoDB & On-Chain | Automated (`pytest`) | All transfers appended sequentially to audit collection | **Blocked** (Route unmapped stub) |

---

## Group E: Integrity & Tamper Detection

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-INT-01 | Three-Way Integrity Check (`VERIFIED`)| `/api/verification/verify` | Automated (`pytest`) | File SHA-256 == MongoDB hash == Blockchain hash -> `VERIFIED` | **Blocked** (Route unmapped stub) |
| TC-INT-02 | File Alteration Detection (`TAMPERED`)| `/api/verification/verify` | Automated (`pytest`) | Modified file hash != registered hash -> `TAMPERED` | **Blocked** (Route unmapped stub) |
| TC-INT-03 | Hash Database / Blockchain Mismatch | `/api/verification/verify` | Automated (`pytest`) | Distinct error codes; not misclassified as simple tampering | **Blocked** (Route unmapped stub) |

---

## Group F: QR & Forensic Reports

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-REP-01 | Forensic PDF Report Generation | `/api/reports/generate` | Automated (`pytest`) | Valid signed PDF generated via ReportLab | **Blocked** (Route unmapped stub) |
| TC-REP-02 | Historical Report Immutability | Generated Reports Store | Automated (`pytest`) | Regeneration creates a new report record; historical intact | **Blocked** (Route unmapped stub) |
| TC-REP-03 | QR Code Verification Routing | `/api/verification/qr` | Automated (`pytest`) | QR payload encodes valid tamper-evident verification link | **Blocked** (Route unmapped stub) |

---

## Group G: Security, Configuration & Audit

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-SEC-01 | Exclude `.env` from Version Control | Git status / filesystem | Automated (`pytest`) | Real `.env` not tracked; only safe `.env.example` committed | **Passed** |
| TC-SEC-02 | CORS Header Restrictions | `app/main.py` | Automated (`pytest`) | CORS allows port 5500; blocks unauthorized origins | **Passed** |
| TC-SEC-04 | Configuration Schema Completeness | `.env.example` | Automated (`pytest`) | All 7 mandatory keys present without real secrets | **Passed** |
| TC-SEC-05 | Git Ignore Storage & Reports Protection| `.gitignore` | Automated (`pytest`) | Rules protect `storage/evidence/*` and `generated_reports/*` | **Passed** |
| TC-SEC-06 | Password Hashing Module Check | `security/password.py` | Automated (`pytest`) | Exposes `hash_password` and `verify_password` | **Blocked** (Security stub) |
| TC-SEC-07 | JWT Expiration Enforcement | `security/auth.py` | Automated (`pytest`) | Expired tokens rejected with HTTP 401 | **Blocked** (Auth stub) |

---

## Group H: Frontend & End-to-End

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-FE-01 | Frontend Scaffolding Integrity | `frontend/` files | Manual file review | HTML/CSS/JS files load cleanly with semantic layout | **Passed** |
| TC-FE-02 | API Health Reachability Check | `frontend/js/api.js` | Integration test | Client polls `/api/health` and toggles status indicator | **Passed** |
| TC-FE-03 | Protected Dashboard Navigation | `dashboard.html` | Integration test | Unauthorized visits redirect to `login.html` | **Blocked** (Static layout) |
