# ChainVault — Test Coverage & Gap Analysis Matrix

This document establishes the comprehensive traceability matrix for Phase 12 validation in accordance with the **ChainVault Phase 12 Acceptance Criteria**, mapping every system requirement to its corresponding test implementation, execution status, coverage gaps, and priority.

---

## 1. Traceability & Coverage Matrix

| Req ID | Component / Area | Expected Behavior | Test File & Name | Execution Status | Coverage Gap | Priority |
|---|---|---|---|---|---|---|
| **REQ-01** | Authentication & JWT | Validate user credentials with bcrypt; issue signed JWT; reject invalid/expired tokens | `tests/test_feature_coverage.py::<br>test_auth_login_endpoint_exists`<br>`tests/test_audit_security.py::<br>test_password_hashing_security_module` | **BLOCKED** | Endpoint `/api/auth/login` unmapped; `security/password.py` and `security/auth.py` are empty stubs | **P0** |
| **REQ-02** | RBAC & Object Auth | Enforce role permissions (Admin, Investigator, Officer); reject unauthorized operations | `tests/test_feature_coverage.py::<br>test_auth_login_endpoint_exists` | **BLOCKED** | `security/permissions.py` is empty stub; no object-level permissions implemented | **P1** |
| **REQ-03** | Case Management & Soft Deletion | Create, retrieve, update cases; soft delete inactive cases; filter from normal queries | `tests/test_feature_coverage.py::<br>test_case_crud_endpoint_exists` | **BLOCKED** | Endpoint `/api/cases` unmapped; `routes/cases.py` is empty stub | **P1** |
| **REQ-04** | Evidence Upload, Download & SHA-256 | Stream upload; calculate SHA-256; store metadata; restrict downloads safely | `tests/test_evidence_hashing.py::<br>test_sha256_cryptographic_correctness`<br>`tests/test_evidence_hashing.py::<br>test_hashing_service_module`<br>`tests/test_feature_coverage.py::<br>test_evidence_upload_endpoint_exists` | **PASS (Crypto)** /<br>**BLOCKED (Upload)** | Algorithmic SHA-256 passes; upload `/api/evidence/upload` and `services/storage.py` are stubs | **P0** |
| **REQ-05** | Duplicate Detection & Validation | Detect identical evidence SHA-256 hashes; reject or flag duplicates | `tests/test_feature_coverage.py::<br>test_evidence_upload_endpoint_exists` | **BLOCKED** | Evidence deduplication logic unwritten in backend | **P1** |
| **REQ-06** | Blockchain Registration & Failures | Register evidence hash on Ethereum contract; emit events; handle reverts & RPC drops | `blockchain/test/EvidenceRegistry.test.js::<br>TC-BC-01 to TC-BC-05`<br>`tests/test_feature_coverage.py` | **PASS (Skeleton)** /<br>**BLOCKED (Registration)** | Deployer admin check passes; `registerEvidence` function missing on `EvidenceRegistry.sol` | **P1** |
| **REQ-07** | Chain of Custody & History | Authorized custodian transfers; append-only audit trail; blockchain sync | `tests/test_feature_coverage.py::<br>test_custody_transfer_endpoint_exists`<br>`blockchain/test/EvidenceRegistry.test.js::<br>TC-BC-04` | **BLOCKED** | Endpoint `/api/custody/transfer` and contract `transferCustody` missing | **P1** |
| **REQ-08** | Three-Way Integrity & Tampering | Tripartite comparison (File vs Mongo vs Blockchain); identify `VERIFIED`, `TAMPERED`, `BLOCKCHAIN_MISMATCH` | `tests/test_feature_coverage.py::<br>test_verification_endpoint_exists`<br>`blockchain/test/EvidenceRegistry.test.js::<br>TC-BC-05` | **BLOCKED** | Endpoint `/api/verification/verify` and comparison service unwritten | **P0** |
| **REQ-09** | QR Generation & Verification | Generate secure QR code containing tamper-evident verification link; verify via scan | `tests/test_feature_coverage.py::<br>test_verification_endpoint_exists` | **BLOCKED** | QR generation and routing unmounted | **P2** |
| **REQ-10** | Forensic PDF Reports & Immutability | Generate signed ReportLab PDF; ensure historic reports are never overwritten | `tests/test_feature_coverage.py::<br>test_report_generation_endpoint_exists` | **BLOCKED** | Endpoint `/api/reports/generate` and `services/report.py` are stubs | **P2** |
| **REQ-11** | Audit Events & Security Controls | Confirm no evidence-delete route; secure headers; verify secrets excluded | `tests/test_security_baseline.py::<br>test_no_evidence_delete_endpoint`<br>`tests/test_security_baseline.py::<br>test_evidence_storage_directory_traversal_protection`<br>`tests/test_audit_security.py::<br>test_gitignore_protects_evidence_and_reports` | **PASS** | Verified zero delete routes exist, directory traversals blocked, Git excludes evidence/reports | **P0** |
| **REQ-12** | Frontend API Integration | Login redirection; health status indicator; CORS authorization for port 5500 | `tests/test_cors.py::<br>test_cors_frontend_port_allowed`<br>`tests/test_health.py::<br>test_health_check_endpoint` | **PASS (Health/CORS)** /<br>**BLOCKED (Auth E2E)** | Health API and CORS pass; live session dashboard E2E blocked by static stub | **P2** |
| **REQ-13** | Configuration Safety & Recovery | Safe `.env.example` keys; isolated `chainvault_test` DB; verify restore capability | `tests/test_audit_security.py::<br>test_env_example_contains_all_required_keys`<br>`tests/test_database_config.py::<br>test_mongodb_client_configuration_defaults`<br>`tests/test_database_config.py::<br>test_live_mongodb_connection` | **PASS (Config)** /<br>**BLOCKED (Live DB)** | Config schemas and defaults verified; live connection blocked by inactive MongoDB service | **P0** |

---

## 2. Gap Prioritization & Impact Analysis

### Priority P0 — Critical Integrity, Security & Data Safety Gaps
*Why it matters: Failures at this level directly cause evidence corruption, false court admissibility, authentication bypass, or data leakage.*
1. **REQ-01 (Authentication Bypass / Unimplemented Auth):** Without bcrypt verification and JWT enforcement, any caller can bypass identity boundaries or access evidence endpoints without credentials.
2. **REQ-04 (Evidence Integrity & SHA-256 Pipeline):** The core premise of ChainVault is cryptographic evidence immutability. If files cannot be safely ingested and hashed via `calculate_hash`, the forensic chain is broken at source.
3. **REQ-08 (Three-Way Integrity Verification):** The platform's central verification mechanism compares local file hashes against database records and the immutable blockchain ledger. Until implemented, false integrity determinations or undetected tampering cannot be validated.
4. **REQ-11 & REQ-13 (Configuration & Database Protection):** Accidental leakage of private keys or mutation of development databases during testing risks irreversible compromise. (Mitigated: Automated tests verify `.env` is outside Git and collection definitions are isolated).

### Priority P1 — Core Business Logic & Blockchain Gaps
*Why it matters: Directly prevents execution of custody transfers, smart contract registrations, and case access control.*
1. **REQ-06 (On-Chain Evidence Registration):** `EvidenceRegistry.sol` lacks `registerEvidence`. Until the contract and transaction submission service are implemented, hashes cannot be anchored on Ethereum.
2. **REQ-07 (Chain-of-Custody Transfers):** The custody transfer lifecycle is the primary legal chain of custody. Without transfer endpoints and event logs, transfers cannot be tracked or audited.
3. **REQ-02 & REQ-03 (Case Management & RBAC):** Case creation and role restrictions are prerequisites for grouping evidence and enforcing investigator boundaries.
4. **REQ-05 (Duplicate Detection):** Without duplicate hash detection, re-uploaded files cannot be correlated with existing evidence entries.

### Priority P2 — Auxiliary Workflows & Reporting Gaps
*Why it matters: Degrades auxiliary forensics workflows and user accessibility, but does not corrupt the core cryptographic chain.*
1. **REQ-09 (QR Code Routing):** Mobile and physical evidence tag verification relies on QR payloads.
2. **REQ-10 (Forensic PDF Reports):** PDF export is required for courtroom presentation and physical evidence binders. Historical immutability must ensure regenerated reports do not overwrite previous audit records.
3. **REQ-12 (Frontend E2E Workflows):** Client-side dashboards currently run in static layout mode without dynamic API token exchange.

### Priority P3 — Cosmetic & Minor Validation Gaps
*Why it matters: Polish, minor documentation mismatches, and test reporting formatting.*
1. Warning logs from deprecated `httpx` imports in test client.
2. Test summary formatting and documentation cross-links.

---

## 3. Prioritized Next Testing Action

1. **Prerequisite:** Project Owner authorization and implementation of Phase 2 (MongoDB + FastAPI) and Phase 3 (Authentication).
2. **Immediate Action:** Start the local MongoDB service (`net start MongoDB` or `mongod`) to unblock `tests/test_database_config.py::test_live_mongodb_connection`.
3. **Subsequent Action:** Once Phase 5/6 smart contract methods are added, update `EvidenceRegistry.test.js` to test `registerEvidence`, duplicate rejection, and events.
