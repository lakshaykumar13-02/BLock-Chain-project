# ChainVault — Security & Forensic Integrity Audit (Phase E)

**Audit Date:** 2026-10-13  
**Audit Author:** Antigravity Master Project Audit Agent  
**Authoritative Workspace:** `D:\parjaayi project\CHAINVAULT`  
**Current Git Branch:** `master`  

---

## 1. Executive Summary

This security and forensic integrity audit evaluates ChainVault’s defensive posture, cryptographic soundness, role-based access control, file handling, smart-contract safety, and legal/forensic boundaries.

All findings are grounded strictly in the codebase, active configurations, and executed test suites.

---

## 2. Cryptographic & Forensic Integrity Controls

### 2.1 SHA-256 Bitstream Hashing
- **Implementation:** `backend/app/services/hashing.py` utilizes Python standard library `hashlib.sha256`.
- **Chunked File Streaming:** Files are read in binary chunks of 65,536 bytes (`64 KB`), ensuring low memory consumption and consistent digests regardless of file size.
- **Verification:** Verified by `test_evidence_hashing.py::test_sha256_cryptographic_correctness`.

### 2.2 Off-Chain Storage Architecture
- **Forensic Principle:** Large evidence binary files must not be stored on-chain due to blockchain block gas limits, prohibitive storage costs, and privacy implications.
- **Implementation:** Physical files are stored strictly on the local filesystem (`backend/storage/evidence/`). Only the cryptographic SHA-256 digest, evidence identifier, and custodian metadata are anchored on the Ethereum smart contract.

### 2.3 Tripartite Hash Verification
- **Endpoint:** `POST /api/verification/verify`.
- **Pairwise Checks Executed:**
  1. `file_vs_database`: Physical disk file re-hashed vs. database recorded digest.
  2. `database_vs_blockchain`: Database recorded digest vs. on-chain smart contract hash.
  3. `file_vs_blockchain`: Physical disk hash vs. on-chain smart contract hash.
- **Safety Standard:** The endpoint requires all pairwise comparisons to evaluate to `True` for `verified: True`. Any mismatch returns `verified: False` and `tampered: True`.
- **Hash Immutability During Verification:** Under no circumstances does a verification failure alter, overwrite, or repair the stored authentic database digest. Verified by `test_data_integrity.py::test_evidence_tampering_mismatch_detection`.

---

## 3. Authentication & Access Control (RBAC)

### 3.1 Password Security
- **Algorithm:** `bcrypt` with automated salt generation (`backend/app/security/password.py`).
- **Storage:** Pre-configured demo accounts (`admin`, `investigator1`, `analyst1`, `viewer1`) store bcrypt hashes. Zero plaintext passwords exist in code or database collections.
- **Verification:** Verified by `test_security_regression.py::test_password_stored_as_bcrypt_hash_not_plaintext`.

### 3.2 JWT Token Architecture
- **Algorithm:** HS256 (`backend/app/security/auth.py`).
- **Payload Claims:** Subject (`sub`), username (`username`), role (`role`), expiration (`exp`).
- **Lifetime:** 30 minutes (`JWT_EXPIRE_MINUTES`).
- **Validation:** Signature and expiration claims verified on every authenticated request. Missing, malformed, or expired tokens are rejected with `HTTP 401 Unauthorized`.

### 3.3 Server-Side Role-Based Access Control Matrix

| Endpoint | ADMIN | INVESTIGATOR | ANALYST | VIEWER |
|---|---|---|---|---|
| `GET /api/cases` | Allowed | Allowed | Allowed | Allowed |
| `POST /api/cases` | **Allowed** | **Allowed** | 403 Forbidden | 403 Forbidden |
| `DELETE /api/cases/{id}` | **Allowed** (Soft-delete) | 403 Forbidden | 403 Forbidden | 403 Forbidden |
| `GET /api/evidence` | Allowed | Allowed | Allowed | Allowed |
| `POST /api/evidence/upload` | **Allowed** | **Allowed** | 403 Forbidden | 403 Forbidden |
| `DELETE /api/evidence/{id}` | **405 Method Not Allowed** | **405 Method Not Allowed** | **405 Method Not Allowed** | **405 Method Not Allowed** |
| `POST /api/blockchain/register` | **Allowed** | **Allowed** | 403 Forbidden | 403 Forbidden |
| `POST /api/custody/transfer` | **Allowed** | **Allowed** | 403 Forbidden | 403 Forbidden |
| `POST /api/reports/generate` | **Allowed** | **Allowed** | **Allowed** | 403 Forbidden |
| `GET /api/reports/download/{f}` | Allowed | Allowed | Allowed | Allowed |
| `GET /api/audit/logs/{id}` | Allowed | Allowed | Allowed | Allowed |
| `GET /api/audit/all` | **Allowed** | **Allowed** | 403 Forbidden | 403 Forbidden |

*Enforcement:* Enforced server-side via `Depends(require_role([...]))`. Client-side UI hiding is strictly a cosmetic UX convenience; direct API requests without the requisite role are blocked by the backend.

---

## 4. Input Validation & Defensive Controls

### 4.1 File Size & Upload Restrictions
- **Ceiling:** Enforces a maximum upload size of 50 MB (`52,428,800 bytes`).
- **Rejection:** Uploads exceeding 50 MB are immediately rejected with `HTTP 413 Content Too Large`.
- **Character Sanitization:** Filenames containing control characters (`\x00`, `\n`, `\r`), directory separators (`/`, `\`), or shell symbols (`<`, `>`, `:`, `"`, `|`, `?`, `*`, `..`) are rejected with `HTTP 400 Bad Request`.

### 4.2 Path Traversal Defenses
- Both evidence downloads (`/api/evidence/download/{filename:path}`) and report downloads (`/api/reports/download/{filename}`) enforce strict path canonicalization:
  ```python
  if not str(file_path).startswith(str(target_dir)):
      raise HTTPException(status_code=404, detail="Access denied")
  ```
- Any attempt to traverse (`../../Windows/win.ini`, `../../.env`, etc.) evaluates to `None` or raises `404 Not Found`.
- Verified by `test_security_regression.py::test_input_path_traversal_evidence_download_blocked` and `test_input_path_traversal_report_download_blocked`.

### 4.3 HTTP Defensive Security Headers
Middleware in `backend/app/main.py` injects standard security headers on every response:
- `X-Content-Type-Options: nosniff` (MIME sniffing prevention)
- `X-Frame-Options: DENY` (Clickjacking prevention)
- `X-XSS-Protection: 1; mode=block` (Cross-site scripting filter)
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (Transport security)

---

## 5. Smart Contract Security

- **Contract:** `blockchain/contracts/EvidenceRegistry.sol`
- **Compiler:** Solidity `^0.8.19` (built-in arithmetic overflow/underflow protection).
- **Access Modifiers:**
  - `onlyAdmin`: Restricts contract administrative operations to deployer address.
  - `evidenceExists`: Prevents lookups and custody transfers on non-existent records.
- **State Immutability:**
  - `registerEvidence` checks `!evidenceRecords[evidenceId].exists`; duplicate registrations revert immediately.
  - Once registered, `fileHash`, `evidenceId`, and `caseId` are immutable; only `custodian` changes via authorized `transferCustody`.
- **Event Logging:** All state changes emit indexed events (`EvidenceRegistered`, `CustodyTransferred`) to the Ethereum event log for independent indexing.

---

## 6. Verification Boundaries & Disclaimers

To maintain strict scientific and forensic accuracy, the project distinguishes between local academic prototype validation and commercial certifications:

| Category | Status in ChainVault | Evidentiary Basis |
|---|---|---|
| **Automated Unit & Integration Tests** | **VERIFIED (100%)** | 102 backend tests, 6 Hardhat tests executed and passing |
| **Local Manual Workflow Verification** | **VERIFIED (100%)** | 14-step end-to-end evidence lifecycle validated |
| **Static Code Analysis** | **VERIFIED** | Code inspected; Pytest and Hardhat compilers clean |
| **Independent Penetration Testing** | **NOT CONDUCTED** | Academic prototype; external pen-test out of scope |
| **Formal Smart Contract Audit** | **NOT CONDUCTED** | Academic prototype; third-party audit out of scope |
| **Legal Admissibility / Court Certification** | **DISCLAIMED** | Academic prototype aligned with ISO/IEC 27037 principles; not certified for court proceedings |
| **Digital Signature Standard** | **SHA-256 Tamper-Evident** | PDF reports utilize SHA-256 file checksums; does not utilize X.509 PKCS#7 digital certificate signing |
