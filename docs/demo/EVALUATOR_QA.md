# ChainVault — Evaluator Technical Q&A Guide

**Target Audience:** Project Evaluators, Examination Panel, BCA / Cybersecurity Defense  
**Scope:** Authoritative, code-grounded answers based strictly on the verified ChainVault repository implementation.

---

### Q1: Why use blockchain for digital evidence integrity?
**Technical Answer:**
Standard relational or document databases (such as MySQL or MongoDB) are managed by centralized database administrators (`dba` / `root`). A malicious or compromised administrator can alter records, modify timestamps, or rewrite audit tables using `UPDATE` or `DROP` commands with zero visible audit trail.

A blockchain provides **append-only, decentralized immutability**. Once a transaction anchoring an evidence cryptographic hash and timestamp is mined into an Ethereum block, it cannot be modified or deleted without rewriting the entire subsequent cryptographic chain across the network. By recording evidence hashes and custody transfers on the Ethereum Virtual Machine (EVM), ChainVault ensures that even a compromised server administrator cannot alter historical evidence records without cryptographic detection.

---

### Q2: Why store files off-chain instead of on the blockchain directly?
**Technical Answer:**
Storing binary files directly on a blockchain is technically and economically impractical:
1. **Gas Cost & Block Limits:** On Ethereum, storing 1 kilobyte of data costs approximately 640,000 gas. A 100 MB forensic file would cost tens of thousands of dollars in gas and exceeds the block gas limit (typically 30 million gas), preventing the block from ever being mined.
2. **Confidentiality & Legal Privacy:** Blockchains are distributed ledgers where all transaction data is replicated to every participating node. Storing sensitive evidence (e.g., criminal case files, surveillance footage, personal communications) directly on-chain would expose confidential investigative data to public or node operators.

ChainVault adopts the **hybrid model**: the actual large binary file is held in secure local filesystem storage (`storage/evidence/`), while only the fixed-size 32-byte (64-character hex) **SHA-256 cryptographic digest** is anchored on-chain. This provides mathematical proof of integrity without gas overhead or privacy exposure.

---

### Q3: How does the SHA-256 verification process work in ChainVault?
**Technical Answer:**
During evidence ingestion (`POST /api/evidence/upload`), the server streams the file content through Python's standard `hashlib.sha256()` algorithm. 

SHA-256 (Secure Hash Algorithm 256-bit) has three vital mathematical properties:
1. **Deterministic:** The exact same input always yields the exact same 64-character hexadecimal digest.
2. **Pre-image Resistance (One-way):** It is computationally infeasible to reconstruct the original evidence file from the hash digest.
3. **Avalanche Effect:** Altering a single bit in a 10 GB file completely randomizes the output digest (approximately 50% of the bits change).

ChainVault captures this hash at ingestion, commits it to MongoDB, and registers it to the Solidity contract `EvidenceRegistry.sol` via `registerEvidence(evidenceId, fileHash, caseId)`.

---

### Q4: What happens if an attacker modifies an evidence file on disk?
**Technical Answer:**
ChainVault's tripartite verification engine (`POST /api/verification/verify`) recalculates the SHA-256 digest directly from the disk file and compares it against both the database record and the blockchain ledger.

If an attacker modifies even a single byte of the file on disk:
1. Recomputed `physical_file_hash` changes to an entirely different digest.
2. The comparison `file_vs_database` evaluates to `False`.
3. The comparison `file_vs_blockchain` evaluates to `False`.
4. The system flags `verified: False` and `tampered: True`.
5. **Critical Forensic Rule:** The endpoint **refuses to overwrite** the database or blockchain records with the tampered hash. The original authentic hashes remain intact, exposing the exact discrepancies to forensic investigators.
6. If the file is deleted from disk, the system flags `file_status: 'missing'` rather than falsely claiming a match.

---

### Q5: How is a chain-of-custody transfer verified?
**Technical Answer:**
When an investigator transfers evidence (`POST /api/custody/transfer`), three synchronized actions occur:
1. **Smart Contract Mutation:** The backend calls `transferCustody(evidenceId, newCustodian, reason)` on `EvidenceRegistry.sol`. The contract verifies the evidence exists, updates `evidenceItems[_evidenceId].custodian = _newCustodian`, and emits the `CustodyTransferred` event with block number and timestamp.
2. **Audit Log Persistence:** An append-only log record (`AUD-<timestamp>`) is created capturing: `previous_custodian`, `new_custodian`, `reason`, `timestamp`, and the confirmed on-chain transaction hash (`tx_hash`).
3. **Ledger Query:** Anyone auditing custody can call `GET /api/blockchain/evidence/{id}` to verify that the on-chain custodian address matches the documented custodian.

---

### Q6: What does the generated QR code contain?
**Technical Answer:**
The QR code generated by `GET /api/reports/qr/{evidence_id}` encodes a direct URI:
`http://localhost:8000/api/verification/verify?evidence_id={evidence_id}`.

When an evidence custodian, laboratory examiner, or judge scans the physical badge attached to an evidence locker bag with a smartphone or barcode reader:
- It initiates an automated query to ChainVault's verification service.
- The service performs the three-way check (Disk vs Mongo vs Chain) and returns the tamper status, current custodian, and on-chain block confirmation without requiring the user to manually type evidence IDs.

---

### Q7: How are user roles and permissions enforced?
**Technical Answer:**
User roles are enforced **server-side** through FastAPI dependency injection (`Depends(require_role([...]))`) in `backend/app/security/permissions.py`. They are never left to client-side JavaScript checks:

1. **`ADMIN`:** Permitted full administrative control and case soft-deletion (`DELETE /api/cases/{id}`).
2. **`INVESTIGATOR`:** Permitted case creation (`POST /api/cases`), evidence upload (`POST /api/evidence/upload`), blockchain registration, and custody transfers.
3. **`ANALYST`:** Permitted tripartite verification, receiving custody, and report generation.
4. **`VIEWER`:** Read-only access (`GET /api/cases`, `GET /api/evidence`). If a VIEWER attempts to upload evidence or transfer custody, FastAPI immediately halts execution and returns `HTTP 403 Forbidden`.

Every protected request must provide a valid signed JSON Web Token (`Authorization: Bearer <token>`) signed with HMAC-SHA256 (`HS256`).

---

### Q8: What happens when MongoDB or the blockchain is unavailable?
**Technical Answer:**
ChainVault implements **graceful degradation and decoupled resilience**:
- **MongoDB Offline:** During application startup (`backend/app/main.py`), the database client attempts to connect to `mongodb://localhost:27017`. If the service is offline or times out, the backend catches `ServerSelectionTimeoutError` and falls back to an internal in-memory state store (`CASES_STORE`, `EVIDENCE_STORE`, `AUDIT_LOGS_STORE`). Core endpoints remain functional for offline analysis.
- **Blockchain Node Offline:** The blockchain service (`backend/app/services/blockchain.py`) incorporates `check_blockchain_health()`. If the local Hardhat node is unreachable on port 8545, `/api/blockchain/status` cleanly reports `"status": "offline"` and queries fall back to internal cryptographic stores without throwing unhandled exceptions or crashing the API.
- **Reconciliation Service:** When connectivity is restored, `POST /api/blockchain/reconcile/{evidence_id}` reconciles on-chain state without issuing duplicate transactions.

---

### Q9: What are the primary security limitations of this implementation?
**Technical Answer:**
In accordance with academic rigor:
1. **File Size Limit (50 MB):** Buffered multipart upload enforces a 50 MB ceiling (`HTTP 413`) to prevent memory exhaustion, whereas real disk images require chunked streaming uploads.
2. **Local Loopback Scope:** Transport uses plain HTTP on loopback `127.0.0.1`. A production system requires TLS/HTTPS certificates, HSTS, and WAF protection.
3. **Shared Signer Key:** For demonstration purposes, transactions are broadcast using Hardhat's test deployer key. Production requires individual officer hardware wallets or KMS-managed private keys.
4. **No Formal Judicial Certification:** The platform implements ISO/IEC 27037 forensic principles, but has not undergone court certification or external third-party penetration testing.

---

### Q10: Why did the project use a local Hardhat network instead of Ethereum Sepolia or Mainnet?
**Technical Answer:**
1. **Zero Transaction Cost & Determinism:** An academic forensic evaluation requires instant, deterministic test execution. Mainnet and testnets incur gas fees, faucet rate-limiting, and network congestion.
2. **Deterministic Block Confirmation:** Hardhat allows instantaneous transaction mining and programmable time manipulation, enabling thorough testing of all 101 automated acceptance test cases in under 30 seconds.
3. **Data Containment:** Testing with public testnets publishes transaction metadata to public block explorers (like Etherscan). A local Hardhat node preserves complete data isolation within the local laboratory environment.
4. **Production Portability:** The contract is written in standard Solidity `^0.8.19` using Hardhat. Switching to a public testnet (such as Sepolia or an enterprise Hyperledger Besu network) requires only changing the `RPC_URL` and `PRIVATE_KEY` in `backend/.env`, with zero changes required to smart contract business logic.
