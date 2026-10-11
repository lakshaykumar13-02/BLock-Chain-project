# ChainVault — Evaluator Demonstration Script (10–15 Minutes)

**Target Audience:** Academic Project Evaluators, Forensics & Cybersecurity Faculty (BCA / Computer Science)  
**System Location:** `d:\parjaayi project\CHAINVAULT` (Authoritative Workspace)  
**Demonstration Scope:** Local Verified Environment (`127.0.0.1`)  
**Verified Checkpoint:** `b3c85c0` (Phase 13.2 Complete & Verified)

---

## Presentation Overview & Timing

| Segment | Topic | Target Time | Interface / Tool |
|---|---|---|---|
| **Part 1** | Problem Statement, Forensics Motivation & Architecture | 2 mins | Presentation / Architecture Diagram |
| **Part 2** | User Authentication & 4-Role RBAC Model | 2 mins | Web UI (`http://127.0.0.1:5500/login.html`) |
| **Part 3** | Case Creation & Secure Evidence Ingestion | 2 mins | Dashboard & REST API (`/api/cases`, `/api/evidence/upload`) |
| **Part 4** | Cryptographic SHA-256 Hashing & On-Chain Anchoring | 2 mins | Hardhat EVM Node & `/api/blockchain/register` |
| **Part 5** | Custody Handover & Chronological Audit Trail | 2 mins | `/api/custody/transfer` & `/api/audit/logs/{id}` |
| **Part 6** | Tripartite Integrity Verification (Disk vs DB vs Chain) | 2 mins | `/api/verification/verify` & Tamper Simulation |
| **Part 7** | Tamper-Evident QR Badges & Signed Forensic PDF | 2 mins | `/api/reports/qr/{id}` & ReportLab PDF Viewer |
| **Part 8** | Defensive Controls, Limitations & Evaluator Q&A | 2 mins | Code Audit & Security Header Inspection |

---

## Detailed Step-by-Step Demonstration Walkthrough

### Part 1: Problem Statement & System Architecture (Minutes 0:00 – 2:00)

#### Speaker Narrative
> "Good morning, respected evaluators. In criminal justice and digital forensics, the greatest vulnerability of digital evidence is **silent tampering** and **broken chain of custody**. Unlike physical evidence locked in a police locker, a digital file (such as a hard drive image, surveillance video, or email archive) can have bits altered with zero visible trace if stored in a standard database or filesystem.
> 
> ChainVault solves this by implementing an **off-chain storage, on-chain cryptographic anchoring** architecture. Large binary evidence files remain in dedicated secure storage, while their mathematical fingerprints—SHA-256 cryptographic hashes—and custody transition events are permanently anchored onto an immutable Ethereum blockchain ledger.
> 
> Today, I will demonstrate the full end-to-end evidence lifecycle running on our verified local environment: from ingestion and on-chain anchoring to custody transfer, tripartite hash verification, QR generation, and forensic PDF reporting."

#### Visual Aid / Key Architecture Points
- **Frontend Layer:** Clean HTML5, CSS3, Vanilla JavaScript (zero third-party JS framework vulnerabilities). Runs on port `5500`.
- **Application Server Layer:** Python 3.13, FastAPI (ASGI) with Pydantic v2 data validation, Bcrypt password hashing, PyJWT authentication, and ReportLab PDF compilation. Runs on port `8000`.
- **Database Layer:** MongoDB Community Server (Windows Service on port `27017`) using Motor asynchronous client, configured with automatic test isolation safeguards (`chainvault_test`).
- **Blockchain Layer:** Ethereum Virtual Machine via Hardhat standalone JSON-RPC node (port `8545`, Chain ID `31337`) running the custom Solidity smart contract `EvidenceRegistry.sol` deployed at `0x5FbDB2315678afecb367f032d93F642f64180aa3`.

---

### Part 2: User Authentication & Role-Based Access Control (Minutes 2:00 – 4:00)

#### Objective
Demonstrate secure authentication and server-side role enforcement across the four defined security roles.

#### Evaluator Action
1. Open web browser to `http://127.0.0.1:5500/login.html`.
2. Review the login interface. Note that demo credentials store precomputed **Bcrypt password hashes** on the backend; zero plaintext passwords exist in database records.
3. Authenticate as Lead Investigator:
   - **Username:** `investigator1`
   - **Password:** `TestPassword123!`
4. Click **Authenticate**.
5. Observe immediate redirection to `dashboard.html`. Note that the system status indicator turns **green** (`Blockchain Network Active`).

#### Behind the Scenes / Code Proof
- The client receives a signed JWT access token (`POST /api/auth/login`).
- Token is safely preserved in browser `sessionStorage` (never in `localStorage`).
- Show the 4-role hierarchy in [permissions.py](file:///d:/parjaayi%20project/CHAINVAULT/backend/app/security/permissions.py):
  - `ADMIN`: System configuration, user management, case soft-deletion.
  - `INVESTIGATOR`: Case creation, evidence upload, blockchain registration, custody transfer.
  - `ANALYST`: Forensic artifact analysis, tripartite verification, custody recipient, report generation.
  - `VIEWER`: Read-only access. Any attempt to upload or mutate state returns `HTTP 403 Forbidden`.

#### Recovery Point
If the browser is closed or token expires, re-authenticate via `login.html` or submit a direct login request via API to obtain a fresh Bearer token.

---

### Part 3: Case Creation & Secure Evidence Ingestion (Minutes 4:00 – 6:00)

#### Objective
Demonstrate creating a new forensic case and ingesting binary evidence with automated SHA-256 calculation.

#### Action
1. **Create Case:** Send request to `POST /api/cases`:
   ```bash
   POST http://127.0.0.1:8000/api/cases
   Headers: Authorization: Bearer <TOKEN>
   Body: {
     "case_id": "CV-DEMO-2026-001",
     "title": "Operation Cyber Vault Demonstration",
     "description": "Synthetic demonstration case for digital forensics verification",
     "lead_investigator": "investigator1"
   }
   ```
   **Expected Output:** `HTTP 201 Created` with timestamp and active status.
2. **Ingest Evidence:** Upload synthetic binary file via `POST /api/evidence/upload`:
   - File: `demo_forensic_payload.dat` (80 bytes)
   - Parameters: `case_id: "CV-DEMO-2026-001"`, `evidence_id: "EV-DEMO-FORENSIC-001"`
   **Expected Output:** `HTTP 201 Created` returning:
   ```json
   {
     "status": "success",
     "evidence_id": "EV-DEMO-FORENSIC-001",
     "file_hash": "f693f6874e7ef95e89643bbf76cafdb06eba9c9aaf7592aafdd8ed8311cad135",
     "file_size": 80
   }
   ```

#### Key Forensics Explanation
> "Notice that upon ingestion, the backend streams the file directly through Python's cryptographic `hashlib` to generate the RFC-compliant SHA-256 digest before writing to disk. The file is placed in `storage/evidence/` with path traversal sanitization, and the hash is committed to the database. At this point, evidence is stored, but not yet anchored on-chain."

---

### Part 4: Cryptographic Verification & On-Chain Anchoring (Minutes 6:00 – 8:00)

#### Objective
Prove that the stored hash matches an independent computation, and anchor the hash onto the Ethereum smart contract.

#### Action
1. **Independent Cryptographic Proof:**
   Show evaluators the terminal command computing SHA-256 independently:
   ```python
   import hashlib
   hashlib.sha256(b"CHAINVAULT_SYNTHETIC_FORENSIC_DISK_IMAGE_PAYLOAD_PHASE_13_DEMO_2026_NON_MODIFIED").hexdigest()
   # Matches: f693f6874e7ef95e89643bbf76cafdb06eba9c9aaf7592aafdd8ed8311cad135
   ```
2. **Register on Blockchain:** Call `POST /api/blockchain/register`:
   ```json
   {
     "evidence_id": "EV-DEMO-FORENSIC-001",
     "hash": "f693f6874e7ef95e89643bbf76cafdb06eba9c9aaf7592aafdd8ed8311cad135",
     "case_id": "CV-DEMO-2026-001"
   }
   ```
   **Expected Output:** `HTTP 200 OK` with confirmed transaction receipt:
   - **Transaction Hash:** `0xdb91...`
   - **Block Number:** #101
   - **Status:** `confirmed`
3. **Verify On-Chain State:** Call `GET /api/blockchain/evidence/EV-DEMO-FORENSIC-001`:
   - Confirms that the smart contract ledger actively stores `f693f6...` and identifies the custodian as the deployer account (`0xf39Fd6...`).

#### Duplicate Protection Feature
> "If a rogue actor attempts to register the same evidence ID a second time, the smart contract's `require(!evidenceItems[_evidenceId].exists, 'Evidence already registered')` statement reverts the transaction immediately. Duplicate evidence tampering is blocked at the EVM bytecode level."

---

### Part 5: Chain of Custody & Audit Trail (Minutes 8:00 – 10:00)

#### Objective
Demonstrate an authorized custody handover and show that every transfer emits an on-chain event and updates the append-only audit trail.

#### Action
1. **Transfer Custody:** Hand over evidence from Investigator to Forensic Analyst:
   ```bash
   POST http://127.0.0.1:8000/api/custody/transfer
   Headers: Authorization: Bearer <TOKEN>
   Body: {
     "evidence_id": "EV-DEMO-FORENSIC-001",
     "new_custodian": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
     "reason": "Transfer to Forensic Lab Analyst for cryptographic artifact verification"
   }
   ```
   **Expected Output:** `HTTP 200 OK` with confirmed on-chain transfer receipt:
   - **Transaction Hash:** `0xcfde...`
   - **Block Number:** #102
   - **New Custodian:** `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`
2. **Inspect Audit History:** Query `GET /api/audit/logs/EV-DEMO-FORENSIC-001`:
   - Returns chronological, append-only entries showing: previous custodian, new custodian, timestamp, handover justification, and transaction hash.

#### Evaluator Highlight
> "In a court of law, opposing counsel often challenges digital evidence by claiming an unauthorized person had access. ChainVault’s audit trail links every custodian handover directly to an immutable on-chain event (`CustodyTransferred`), providing undeniable mathematical proof of possession timeline."

---

### Part 6: Tripartite Hash Verification & Tamper Detection (Minutes 10:00 – 12:00)

#### Objective
Demonstrate ChainVault's signature security capability: three-way independent comparison between physical file, MongoDB metadata, and the blockchain ledger.

#### Action
1. **Verify Authentic State:** Call `POST /api/verification/verify`:
   ```json
   { "evidence_id": "EV-DEMO-FORENSIC-001" }
   ```
   **Expected Output:** `HTTP 200 OK`:
   - `physical_file_hash`: `f693f6...`
   - `database_hash`: `f693f6...`
   - `blockchain_hash`: `f693f6...`
   - `verified`: `true`
   - `tampered`: `false`
2. **Explain Tamper Detection Behavior (BUG-07 Resolution):**
   > "If an attacker gains root access to the filesystem and alters even one byte of `demo_forensic_payload.dat`, the recomputed physical hash changes. The verification endpoint detects that `file_vs_database` is `false`, flags `verified: false, tampered: true`, while **refusing to overwrite** the database or blockchain hashes. The evidence of tampering is permanently exposed.
   > 
   > Furthermore, if the file is deleted from disk, the system flags `file_status: 'missing'` rather than falsely assuming a match."

---

### Part 7: Tamper-Evident QR Badges & Forensic PDF Report (Minutes 12:00 – 14:00)

#### Objective
Show exportable forensic artifacts for physical evidence lockers and courtroom presentation.

#### Action
1. **Stream QR Code Badge:**
   - Call `GET http://127.0.0.1:8000/api/reports/qr/EV-DEMO-FORENSIC-001`.
   - Returns a live dynamic PNG image stream (1682 bytes).
   - Scanning the QR badge navigates directly to the verification page for instant mobile/tablet authentication by court officers or evidence custodians.
2. **Generate Forensic PDF Report:**
   - Call `POST /api/reports/generate` with `case_id: "CV-DEMO-2026-001"`.
   - Returns generated filename: `ChainVault_Forensic_Report_CV-DEMO-2026-001_<timestamp>.pdf`.
   - Shows case metadata, all evidence items, SHA-256 digests, and complete custody timeline.
   - Computes independent SHA-256 digest of the PDF file (`34baa5...`) to ensure the report itself cannot be tampered with.
3. **Download & View:**
   - Access `GET /api/reports/download/{filename}`.
   - Show evaluators the compiled PDF with official header and cryptographic signatures.

---

### Part 8: Defensive Controls, Immutability & Conclusion (Minutes 14:00 – 15:00)

#### Objective
Demonstrate active defensive safeguards and wrap up.

#### Live Security Probes
1. **Evidence Immutability:** Attempt `DELETE /api/evidence/EV-DEMO-FORENSIC-001`.
   - **Result:** Rejected with **`HTTP 405 Method Not Allowed`**. The platform provides zero delete endpoints for evidence; evidence is permanently immutable.
2. **Role Violation:** Attempt to upload evidence using a read-only account (`viewer1`).
   - **Result:** Rejected with **`HTTP 403 Forbidden`**.
3. **Path Traversal Defense:** Attempt `GET /api/reports/download/..%2f..%2fsecret.txt`.
   - **Result:** Rejected with **`HTTP 404 / 400`**. Canonical path containment strictly restricts reads to `generated_reports/`.

#### Evaluator Wrap-Up
> "In summary, ChainVault provides a complete, forensically sound implementation of digital evidence integrity. By combining FastAPI's high performance, MongoDB's flexible schema storage, and Ethereum's decentralized immutability, the platform ensures that digital evidence remains tamper-evident, auditable, and legally defensible.
> 
> Thank you, and I am now ready to answer any questions."

---

## Demonstration Failure Recovery Points

If an unexpected glitch occurs during the live demonstration, use these immediate recovery procedures:

| Failure Scenario | Immediate Recovery Action |
|---|---|
| **Token Expired (HTTP 401)** | Re-login via `http://127.0.0.1:5500/login.html` or issue `POST /api/auth/login` to obtain fresh Bearer token. |
| **Hardhat Standalone Node Inactive** | Check background task `task-1453` or run `cd blockchain && npx hardhat node`. Deploy contract with `npx hardhat run scripts/deploy.js --network localhost`. |
| **MongoDB Connection Failure** | Verify Windows Service `MongoDB` is running: `Get-Service -Name MongoDB`. The backend automatically operates in resilient in-memory mode if the service is interrupted. |
| **Duplicate Evidence ID (HTTP 400/500)** | Append a timestamp or increment ID (e.g., `EV-DEMO-FORENSIC-002`) to generate a unique on-chain entry. |
| **Port Conflict on 8000 or 5500** | Inspect listeners using `Get-NetTCPConnection -LocalPort 8000` and restart daemon via documented runbook. |
