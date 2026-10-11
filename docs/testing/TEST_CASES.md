# ChainVault — Test Cases Specification

This document details all test cases defined for Phase 12 validation in accordance with the **ChainVault Test Execution Plan**.

---

## Group A: Backend and Database

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-BACK-01 | Health Check Endpoint | `/api/health` | Automated (`pytest`) | Returns HTTP 200 with `status: "ok"` | **Passed** |
| TC-BACK-02 | Unmapped Route 404 Handling | `/api/nonexistent` | Automated (`pytest`) | Returns HTTP 404 Not Found | **Passed** |
| TC-BACK-03 | MongoDB Service Connectivity | Port 27017 | PowerShell `Test-NetConnection` | Active TCP socket connection on port 27017 | **Blocked** (Service not running) |
| TC-BACK-04 | User Authentication & JWT Login | `/api/auth/login` | Automated (`pytest`) | Valid credentials return JWT; invalid return 401 | **Blocked** (Route unmapped stub) |
| TC-BACK-05 | Case Creation & Metadata | `/api/cases` | Automated (`pytest`) | Valid payload persists case; returns 201 | **Blocked** (Route unmapped stub) |
| TC-BACK-06 | Case Soft Deletion & Query Filter | `/api/cases/{id}` | Automated (`pytest`) | Deleted case marked inactive, excluded from normal queries | **Blocked** (Route unmapped stub) |
| TC-BACK-07 | Role-Based Access Control (RBAC) | Secure endpoints | Automated (`pytest`) | Unauthorized roles receive HTTP 403 Forbidden | **Blocked** (Security stub) |

---

## Group B: Evidence Management

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-EVID-01 | Confirmation of No Delete Endpoint | `/api/evidence/{id}` | Automated (`pytest`) | HTTP DELETE returns 404 (No delete endpoint exists) | **Passed** |
| TC-EVID-02 | Evidence Upload & SHA-256 Storage | `/api/evidence/upload` | Automated (`pytest`) | File accepted, SHA-256 calculated & stored in DB | **Blocked** (Route unmapped stub) |
| TC-EVID-03 | Duplicate Hash Handling | `/api/evidence/upload` | Automated (`pytest`) | Identical hash detected and flagged/handled | **Blocked** (Route unmapped stub) |
| TC-EVID-04 | Storage Directory Traversal Defense | `/api/evidence/download/..` | Automated (`pytest`) | Traversals rejected with 404 / 400 | **Passed** |

---

## Group C: Blockchain Integration

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-BC-01 | Contract Compilation | `EvidenceRegistry.sol` | Hardhat (`compile`) | Clean compilation with zero Solidity errors | **Passed** |
| TC-BC-02 | Contract Deployer Admin Verification | `EvidenceRegistry.sol` | Hardhat (`test`) | Deployer address matches `admin` state variable | **Passed** |
| TC-BC-03 | Evidence Registration on Chain | `EvidenceRegistry.sol` | Hardhat (`test`) | `registerEvidence` emits event & records hash | **Blocked** (Contract is Phase 1 skeleton) |
| TC-BC-04 | Duplicate Evidence Registration Rejection| `EvidenceRegistry.sol` | Hardhat (`test`) | Contract reverts on re-registering existing evidence ID | **Blocked** (Contract is Phase 1 skeleton) |
| TC-BC-05 | Zero Private Key Leakage | Backend & Frontend | Static audit | No private keys present in DB or client bundles | **Passed** |

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

## Group G: Security & Secrets

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-SEC-01 | Exclude `.env` from Version Control | Git status / filesystem | Automated (`pytest`) | Real `.env` not tracked; only safe `.env.example` committed | **Passed** |
| TC-SEC-02 | CORS Header Restrictions | `app/main.py` | Automated audit | CORS limited to authorized frontend origins (5500, 8000) | **Defect Identified** (5500 missing from CORS origins in `main.py`) |
| TC-SEC-03 | JWT Signing Expiration Validation | `security/auth.py` | Automated (`pytest`) | Expired tokens rejected with HTTP 401 | **Blocked** (Auth stub) |

---

## Group H: Frontend & End-to-End

| Test Case ID | Test Name | Target Component | Method / Suite | Expected Result | Status |
|---|---|---|---|---|---|
| TC-FE-01 | Frontend Scaffolding Integrity | `frontend/` files | Manual file review | HTML/CSS/JS files load cleanly with semantic layout | **Passed** |
| TC-FE-02 | API Health Reachability Check | `frontend/js/api.js` | Integration test | Client polls `/api/health` and toggles status indicator | **Passed** |
| TC-FE-03 | Protected Dashboard Navigation | `dashboard.html` | Integration test | Unauthorized visits redirect to `login.html` | **Blocked** (Frontend is Phase 1 static layout) |
