# ChainVault — API Endpoint Inventory

**Audit Date:** 2026-10-11  
**Project Root:** `C:\ChainVault` (Local: `d:/parjaayi project/CHAINVAULT`)  
**Specification Reference:** Master Specification Phase 2, 3, 4, 6, 7, 8, 9, 10, 11  
**Total Public FastAPI Endpoints:** 20  
**Internal Blockchain JSON-RPC Methods:** 6  

---

## 1. Public FastAPI Application Endpoints

### 1.1 Authentication & Identity

#### `POST /api/auth/login`
- **Router / Handler:** [auth.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/auth.py) `::` `login`
- **Authentication Required:** None (Public)
- **Allowed Roles:** All callers
- **Request Parameters & Body:**
  - Content-Type: `application/json`
  - Schema: `LoginRequest`
    - `username` (string, required): User badge / ID
    - `password` (string, required): Plaintext password for bcrypt verification
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `TokenResponse`
    - `access_token` (string): Signed HS256 JWT
    - `token_type` (string): `"bearer"`
    - `user_id` (string): User identifier
    - `role` (string): Assigned role (`ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`)
- **Error Responses:**
  - `401 Unauthorized`: Invalid credentials (`"Invalid username or password"`)
  - `422 Unprocessable Entity`: Missing fields
- **Frontend Consumers:** [auth.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/auth.js) `loginUser()`
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_01_authenticate` (**PASS**)
  - `tests/test_feature_coverage.py::test_auth_login_endpoint_exists` (**PASS**)
  - `tests/test_api_contract_security.py::test_zero_credentials_leaked_in_api_responses` (**PASS**)

---

### 1.2 Case Management

#### `POST /api/cases`
- **Router / Handler:** [cases.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/cases.py) `::` `create_case`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`
- **Request Parameters & Body:**
  - Content-Type: `application/json`
  - Schema: `CaseCreate`
    - `case_number` (string, optional): Forensic case identifier (e.g. `"CV-2026-001"`)
    - `case_id` (string, optional): Internal ID alias
    - `title` (string, required): Case title
    - `description` (string, optional): Case overview
- **Successful Response:**
  - Status: `201 Created`
  - Schema: `CaseResponse`
    - `case_id` (string): Assigned unique case identifier
    - `case_number` (string): Assigned case reference number
    - `title` (string): Case title
    - `description` (string): Case description
    - `created_at` (string): ISO 8601 UTC timestamp
    - `is_deleted` (boolean): `false`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: Role lacks permission (`VIEWER`, `ANALYST`)
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `fetchCases()`
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_02_create_case` (**PASS**)
  - `tests/integration/test_fastapi_mongodb.py::test_fastapi_case_creation_and_retrieval_integration` (**PASS**)
  - `tests/test_api_contract_security.py::test_protected_endpoints_reject_missing_token` (**PASS**)
  - `tests/test_api_contract_security.py::test_role_enforcement_viewer_cannot_mutate_state` (**PASS**)

#### `GET /api/cases`
- **Router / Handler:** [cases.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/cases.py) `::` `list_cases`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters & Body:** None
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `list[CaseResponse]` (active cases excluding soft-deleted)
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `fetchCases()`, [dashboard.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/dashboard.js)
- **Existing Tests:**
  - `tests/test_api_contract_security.py::test_protected_endpoints_reject_invalid_token` (**PASS**)

#### `GET /api/cases/{case_id}`
- **Router / Handler:** [cases.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/cases.py) `::` `get_case`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `case_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `CaseResponse`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `404 Not Found`: Case does not exist or has been soft-deleted
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js)
- **Existing Tests:**
  - `tests/test_api_contract_security.py::test_role_enforcement_admin_can_soft_delete_case` (**PASS**)

#### `DELETE /api/cases/{case_id}`
- **Router / Handler:** [cases.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/cases.py) `::` `soft_delete_case`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`
- **Request Parameters:** Path parameter `case_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "success", "message": "Case {case_id} soft-deleted"}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: Non-admin role attempting deletion
  - `404 Not Found`: Case does not exist
- **Frontend Consumers:** Administrative case console
- **Existing Tests:**
  - `tests/test_api_contract_security.py::test_role_enforcement_admin_can_soft_delete_case` (**PASS**)
  - `tests/test_api_contract_security.py::test_role_enforcement_investigator_permissions` (**PASS**)

---

### 1.3 Evidence Management

#### `POST /api/evidence/upload`
- **Router / Handler:** [evidence.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/evidence.py) `::` `upload_evidence`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`
- **Request Parameters & Body:**
  - Content-Type: `multipart/form-data`
  - Parameters:
    - `file` (UploadFile, binary): Raw digital evidence binary
    - `case_id` (Form string, optional): Linked case ID (default `"CV-2026-001"`)
    - `evidence_id` (Form string, optional): Assigned ID (defaults sequentially to `"EV-001"`, etc.)
    - `custodian` (Form string, optional): Ingesting custodian badge
- **Successful Response:**
  - Status: `201 Created`
  - Schema: `{"status": "success", "evidence_id": str, "case_id": str, "filename": str, "file_hash": str, "file_size": int, "uploaded_at": str}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: `VIEWER` or unauthorized caller
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `fetchEvidence()`
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_03_upload_synthetic_evidence` (**PASS**)
  - `tests/test_feature_coverage.py::test_evidence_upload_endpoint_exists` (**PASS**)
  - `tests/test_api_contract_security.py::test_protected_endpoints_reject_missing_token` (**PASS**)

#### `GET /api/evidence`
- **Router / Handler:** [evidence.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/evidence.py) `::` `list_evidence`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** None
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `list[dict]`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `fetchEvidence()`, [dashboard.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/dashboard.js)
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py` (**PASS**)

#### `GET /api/evidence/{evidence_id}`
- **Router / Handler:** [evidence.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/evidence.py) `::` `get_evidence`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `evidence_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `dict` (Evidence record metadata)
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `404 Not Found`: Evidence ID not found
- **Frontend Consumers:** Evidence detail modal
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py` (**PASS**)

#### `GET /api/evidence/download/{filename:path}`
- **Router / Handler:** [evidence.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/evidence.py) `::` `download_evidence`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `filename` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: Binary `FileResponse`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `404 Not Found`: File not found or path traversal attempt rejected
- **Frontend Consumers:** Evidence file download link
- **Existing Tests:**
  - `tests/test_security_baseline.py::test_evidence_storage_directory_traversal_protection` (**PASS**)

#### `DELETE /api/evidence/*` (Strict Non-Existence)
- **Behavior:** Unmounted route / HTTP 405 Method Not Allowed / 404
- **Security Rule:** Digital evidence deletion is strictly forbidden by policy.
- **Existing Tests:**
  - `tests/test_security_baseline.py::test_no_evidence_delete_endpoint` (**PASS**)
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_11_attempt_unauthorized_destructive_action` (**PASS**)
  - `tests/test_api_contract_security.py::test_evidence_deletion_rejected_for_admin` (**PASS**)

---

### 1.4 Blockchain Integration

#### `POST /api/blockchain/register`
- **Router / Handler:** [blockchain.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/blockchain.py) `::` `register_evidence`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`
- **Request Parameters & Body:**
  - Content-Type: `application/json`
  - Schema: `BlockchainRegisterRequest`
    - `evidence_id` (string, required): e.g. `"EV-001"`
    - `hash` (string, required): 64-character SHA-256 digest
    - `case_id` (string, optional): Associated case ID
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "success", "message": str, "tx_hash": str, "block_number": int, "receipt": dict}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: Unauthorized caller
- **Frontend Consumers:** Evidence registration modal
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_05_register_evidence_on_blockchain` (**PASS**)
  - `tests/integration/test_fastapi_blockchain.py::test_blockchain_service_integration_module` (**PASS**)

#### `GET /api/blockchain/status`
- **Router / Handler:** [blockchain.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/blockchain.py) `::` `blockchain_status`
- **Authentication Required:** None (Public)
- **Allowed Roles:** All callers
- **Request Parameters:** None
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "online"|"offline", "rpc_url": "http://127.0.0.1:8545", "network": "Hardhat Local Testnet"}`
- **Error Responses:** None
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `fetchBlockchainStatus()`, [dashboard.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/dashboard.js)
- **Existing Tests:**
  - `tests/integration/test_fastapi_blockchain.py::test_blockchain_rpc_graceful_handling_when_node_offline` (**PASS**)
  - `tests/test_api_contract_security.py::test_zero_credentials_leaked_in_api_responses` (**PASS**)

#### `GET /api/blockchain/evidence/{evidence_id}`
- **Router / Handler:** [blockchain.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/blockchain.py) `::` `get_blockchain_evidence`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `evidence_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `dict` (On-chain record receipt)
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `404 Not Found`: Evidence not registered on blockchain
- **Frontend Consumers:** Blockchain audit panel
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py` (**PASS**)

---

### 1.5 Chain of Custody & Audit

#### `POST /api/custody/transfer`
- **Router / Handler:** [custody.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/custody.py) `::` `transfer_custody`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`
- **Request Parameters & Body:**
  - Content-Type: `application/json`
  - Schema: `CustodyTransferRequest`
    - `evidence_id` (string, optional, default `"EV-001"`)
    - `new_custodian` (string, optional, default `"officer2"`)
    - `reason` (string, optional)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "success", "message": str, "record": dict, "blockchain": dict}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: Non-investigator/admin caller
- **Frontend Consumers:** Custody transfer dialog
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_06_transfer_custody` (**PASS**)
  - `tests/test_feature_coverage.py::test_custody_transfer_endpoint_exists` (**PASS**)
  - `tests/test_api_contract_security.py::test_role_enforcement_viewer_cannot_mutate_state` (**PASS**)

#### `GET /api/custody/history/{evidence_id}`
- **Router / Handler:** [custody.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/custody.py) `::` `get_custody_history`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `evidence_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `list[dict]`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
- **Frontend Consumers:** Custody timeline view
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py` (**PASS**)

#### `GET /api/audit/logs/{evidence_id}`
- **Router / Handler:** [audit.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/audit.py) `::` `get_evidence_audit_logs`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `evidence_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "success", "evidence_id": str, "logs": list[dict], "count": int}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
- **Frontend Consumers:** Audit trail modal
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_10_inspect_audit_records` (**PASS**)

#### `GET /api/audit/all`
- **Router / Handler:** [audit.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/audit.py) `::` `get_all_audit_logs`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`
- **Request Parameters:** None
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"total": int, "logs": list[dict]}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: `VIEWER` or `ANALYST` role
- **Frontend Consumers:** Compliance & Security Overview panel
- **Existing Tests:**
  - `tests/test_api_contract_security.py` (**PASS**)

---

### 1.6 Three-Way Integrity Verification

#### `POST /api/verification/verify`
- **Router / Handler:** [verification.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/verification.py) `::` `verify_evidence_integrity`
- **Authentication Required:** None (Public for cryptographic tamper-check)
- **Allowed Roles:** All callers
- **Request Parameters & Body:**
  - Content-Type: `application/json`
  - Schema: `VerificationRequest`
    - `evidence_id` (string, optional, default `"EV-001"`)
    - `check_hash` (string, optional): External comparator digest
- **Successful Response:**
  - Status: `200 OK`
  - Schema:
    - `status`: `"success"`
    - `evidence_id`: string
    - `verified`: boolean (true if all 3 match)
    - `tampered`: boolean (true if any comparison fails)
    - `physical_file_hash`: 64-char string
    - `database_hash`: 64-char string
    - `blockchain_hash`: 64-char string
    - `comparisons`: `{"file_vs_database": bool, "database_vs_blockchain": bool, "file_vs_blockchain": bool}`
    - `verified_at`: ISO timestamp string
- **Error Responses:** None (Graceful calculation)
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `verifyEvidence()`, [dashboard.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/dashboard.js)
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_07_three_way_hash_verification` (**PASS**)
  - `tests/test_feature_coverage.py::test_verification_endpoint_exists` (**PASS**)

---

### 1.7 Forensic Reports & QR Badges

#### `GET /api/reports/qr/{evidence_id}`
- **Router / Handler:** [reports.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/reports.py) `::` `get_evidence_qr`
- **Authentication Required:** None (Public for scanner badges)
- **Allowed Roles:** All callers
- **Request Parameters:** Path parameter `evidence_id` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Content-Type: `image/png` (Raw QR image stream)
- **Error Responses:** None
- **Frontend Consumers:** QR scan badge display
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_08_generate_qr_code` (**PASS**)

#### `POST /api/reports/generate`
- **Router / Handler:** [reports.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/reports.py) `::` `generate_forensic_report`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`
- **Request Parameters & Body:**
  - Content-Type: `application/json`
  - Schema: `ReportGenerateRequest`
    - `case_id` (string, optional, default `"CV-2026-001"`)
    - `title` (string, optional)
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "success", "message": str, "case_id": str, "report_filename": str, "report_path": str}`
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `403 Forbidden`: `VIEWER` role
- **Frontend Consumers:** Report generation console
- **Existing Tests:**
  - `tests/integration/test_evidence_lifecycle.py::test_lifecycle_step_09_generate_forensic_pdf_report` (**PASS**)
  - `tests/test_feature_coverage.py::test_report_generation_endpoint_exists` (**PASS**)

#### `GET /api/reports/download/{filename}`
- **Router / Handler:** [reports.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/routes/reports.py) `::` `download_report`
- **Authentication Required:** Yes (`Bearer <token>`)
- **Allowed Roles:** `ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`
- **Request Parameters:** Path parameter `filename` (string)
- **Successful Response:**
  - Status: `200 OK`
  - Content-Type: `application/pdf` (FileResponse)
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid JWT
  - `404 Not Found`: Report file not found
- **Frontend Consumers:** Court report download link
- **Existing Tests:**
  - `tests/test_api_contract_security.py` (**PASS**)

---

### 1.8 System Health

#### `GET /api/health`
- **Router / Handler:** [main.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/main.py) `::` `health_check`
- **Authentication Required:** None (Public)
- **Allowed Roles:** All callers
- **Request Parameters:** None
- **Successful Response:**
  - Status: `200 OK`
  - Schema: `{"status": "ok", "service": "ChainVault API"}`
- **Error Responses:** None
- **Frontend Consumers:** [api.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) `checkApiHealth()`, [dashboard.js](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/dashboard.js)
- **Existing Tests:**
  - `tests/test_health.py::test_health_check_endpoint` (**PASS**)
  - `tests/integration/test_frontend_fastapi.py::test_frontend_api_health_endpoint_integration` (**PASS**)

---

## 2. Internal Blockchain Service & Solidity Functions

These methods operate strictly at the smart contract / JSON-RPC layer on `http://127.0.0.1:8545` and are consumed exclusively by [blockchain.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/services/blockchain.py).

| Function Name | Signature & Parameters | Modifiers | Access Control | Emitted Events | Tested In |
|---|---|---|---|---|---|
| `admin` | `() external view returns (address)` | `view` | Public | None | `TC-BC-01` (**PASS**) |
| `registerEvidence` | `(string evidenceId, string caseId, string fileHash) external` | Public | Open / Caller is custodian | `EvidenceRegistered` | `TC-BC-03` (**PASS**) |
| `registerEvidence` (overload) | `(string evidenceId, string fileHash) external` | Public | Open / Caller is custodian | `EvidenceRegistered` | `TC-BC-04` (**PASS**) |
| `transferCustody` | `(string evidenceId, address newCustodian, string reason) external` | `evidenceExists` | Custodian or Admin | `CustodyTransferred` | `TC-BC-04` (**PASS**) |
| `verifyEvidence` | `(string evidenceId, string checkHash) external view returns (bool)` | `view`, `evidenceExists` | Public view | None | `TC-BC-05` (**PASS**) |
| `getEvidence` | `(string evidenceId) external view returns (string, string, string, address, uint256)` | `view`, `evidenceExists` | Public view | None | `TC-BC-03` (**PASS**) |
| `doesEvidenceExist` | `(string evidenceId) external view returns (bool)` | `view` | Public view | None | `TC-BC-03` (**PASS**) |
| `getCustodyHistoryCount` | `(string evidenceId) external view returns (uint256)` | `view`, `evidenceExists` | Public view | None | `TC-BC-04` (**PASS**) |
