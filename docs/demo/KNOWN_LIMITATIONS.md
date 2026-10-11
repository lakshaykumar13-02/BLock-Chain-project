# ChainVault — Known Limitations & Scope Disclaimers

**System Location:** `d:\parjaayi project\CHAINVAULT`  
**Evaluation Scope:** Academic / Forensic Prototype (Phase 13 Verified)  
**Status:** Strictly Supported by Actual Codebase & Audit Evidence

---

## 1. Prototype Scope vs. Production Deployment

ChainVault is currently implemented and validated as an **academic prototype and forensic proof-of-concept**. It is designed to demonstrate the feasibility, cryptographic architecture, and tamper-evident guarantees of combining off-chain storage with on-chain Ethereum ledger anchoring.

The following architectural distinctions apply between the current verified implementation and a future production-grade system:

| Functional Area | Current Local Prototype (Verified) | Production-Grade Requirement |
|---|---|---|
| **Blockchain Network** | Local Hardhat EVM standalone JSON-RPC node (`http://127.0.0.1:8545`, Chain ID `31337`). Zero gas fees, instantaneous deterministic mining. | Public/Enterprise Ethereum testnet or private consortium network (e.g., Hyperledger Besu, Polygon, Ethereum PoS). Requires real gas fee management, transaction mempools, and block confirmation delays. |
| **Smart Contract Key Management** | Fixed local Hardhat test signer (`0xf39Fd6...`) configured via backend service. | Hardware Security Module (HSM), multi-signature governance (e.g., Gnosis Safe), or decentralized key management for forensic officers. |
| **Evidence Physical Storage** | Local filesystem storage (`storage/evidence/`) with path traversal sanitization and 50 MB upload ceiling. | Redundant distributed storage (e.g., private IPFS cluster, encrypted AWS S3 with Object Lock WORM storage, or Ceph). |
| **Database Architecture** | Standalone MongoDB Community Server on local port `27017` with in-memory resilient fallback. | MongoDB Replica Set with multi-node replication, automated failover, TLS transport encryption, and encrypted at rest (WiredTiger encryption). |
| **Transport Security** | Local HTTP on loopback `127.0.0.1`. Defensive HTTP headers injected (`X-Frame-Options`, `X-Content-Type-Options`). | Enforced HTTPS with valid TLS/SSL certificates from an accredited Certificate Authority, strict HSTS, and reverse proxy (e.g., Nginx, Traefik). |
| **User Directory** | In-memory bcrypt user registry (`DEMO_USERS`) with 4-role RBAC enforcement. | Enterprise Identity Provider integration (e.g., Active Directory / LDAP, SAML 2.0, or OAuth2 / OpenID Connect with multi-factor authentication). |

---

## 2. Technical & Performance Limitations

### A. Ingestion File Size Threshold
- **Observed Behavior:** The evidence upload route `POST /api/evidence/upload` enforces a hard ceiling of **50 MB** (`HTTP 413 Payload Too Large`).
- **Rationale:** Designed to prevent denial-of-service (DoS) via memory exhaustion on standard student/examiner machines.
- **Limitation:** Raw forensic disk images in real criminal investigations frequently range from 256 GB to several terabytes. Ingestion of multi-gigabyte forensic disk images would require chunked streaming uploads (e.g., tus protocol) and direct disk streaming rather than buffered multipart form uploads.

### B. Single Server Deployment Boundary
- Currently, all services (Hardhat node, MongoDB, FastAPI, and frontend HTTP server) operate on a single host machine across local ports (`8545`, `27017`, `8000`, `5500`).
- Network latency, distributed clock drift, and multi-node Byzantine fault tolerance have not been tested across physically distinct networks.

### C. Offline Blockchain Resilient Fallback
- When the local Hardhat node is offline, the backend transitions gracefully to an internal in-memory chain state store (`CHAIN_EVIDENCE_STORE`).
- While this ensures high availability during testing, in a production legal environment, failure to reach the blockchain must raise a high-severity operational alert and pause evidence registration until consensus is restored.

### D. Audit Trail Scope vs. Unified Event Bus
- **Observed Implementation:** `GET /api/audit/logs/{id}` specifically queries `AUDIT_LOGS_STORE`, which records custody transfer operations (`CUSTODY_TRANSFER`) and synthesizes initial ingestion provenance (`EVIDENCE_INGESTION`) if queried before any transfers occur.
- **Limitation:** General system lifecycle operations (case creation, file uploads, tripartite verification executions, and PDF downloads) are recorded in their respective domain stores (`CASES_STORE`, `EVIDENCE_STORE`, `reports/`) and on-chain, but are not aggregated into a centralized, unified SIEM audit log stream.

### E. Forensic PDF Checksum vs. Asymmetric Digital Signature
- **Observed Implementation:** Report generation (`generate_pdf_report`) compiles case details, evidence digests, and custody history into a PDF and computes its cryptographic SHA-256 digest (`report_hash`).
- **Limitation:** This SHA-256 hash provides tamper-evident file verification (detecting post-generation modifications). However, it does **not** constitute an asymmetric cryptographic digital signature (such as an X.509 PKCS#7 or PAdES certificate signature using a forensic officer's private key and certified PKI infrastructure).

### F. QR Code Localhost URL & External Mobile Scanning
- **Observed Implementation:** `GET /api/reports/qr/{id}` generates a QR code encoding `http://localhost:8000/api/verification/verify?evidence_id={id}`.
- **Limitation:** In a local development environment, `localhost` resolves to the loopback interface of the scanning device. Scanning this QR badge with an external smartphone or tablet attempts to connect to `127.0.0.1` on the smartphone itself, failing to reach the host computer. For external mobile scanning to function, the server must be configured with a reachable LAN IP address or reverse proxy.

### G. In-Memory Fallback Volatility vs. Durable Storage
- **Observed Implementation:** The application provides fallback stores (`CASES_STORE`, `EVIDENCE_STORE`, `AUDIT_LOGS_STORE`) when MongoDB is disconnected or in test fixtures.
- **Limitation:** In-memory fallback resides purely in Python process RAM. It is volatile and completely lost if the FastAPI backend process (Uvicorn) is restarted. Durable persistence across restarts requires the MongoDB Community Server service to be active and connected.

### H. Local Hardhat Ephemeral Chain State
- **Observed Implementation:** The blockchain ledger runs on a local Hardhat standalone node (`http://127.0.0.1:8545`, Chain ID `31337`).
- **Limitation:** Local Hardhat chain state is ephemeral. Restarting the `npx hardhat node` process resets the block height to 0 and clears all previously mined transactions and deployed contracts. Deploying a fresh contract produces a new address, and historical transaction hashes from prior node sessions become invalid on the reset chain.

---

## 3. Legal & Compliance Disclaimers

### A. Legal Admissibility Disclaimer
- **No Formal Judicial Precedent:** ChainVault provides technical mechanisms designed to comply with principles of **ISO/IEC 27037:2012** (Guidelines for identification, collection, acquisition, and preservation of digital evidence) and **Federal Rule of Evidence 902(13)/(14)** (Self-authenticating digital records).
- **Academic Status:** This implementation has **NOT** been certified by NIST (National Institute of Standards and Technology), the FBI Regional Computer Forensics Laboratories, or any judicial courtroom. It cannot be represented as legally certified court-admissible software without formal judicial review and independent forensic laboratory validation.

### B. Security & Penetration Testing Disclaimer
- **Audit Scope:** The platform has been rigorously audited against internal regression suites, unit tests, API contract tests, and input security test suites (covering path traversal, role violations, forbidden filename characters, and credential leak defense).
- **Limitation:** The platform has **NOT** undergone an independent third-party penetration test, red-team exercise, or formal smart contract audit by an external cybersecurity firm (e.g., CertiK, OpenZeppelin, Trail of Bits).

---

## 4. Planned Future Roadmap

1. **IPFS / Distributed File Storage Integration:** Replace local disk storage with private IPFS cluster pinned by authenticated forensic nodes.
2. **Chunked Streaming for Large Forensic Images (E01/DD):** Implement resumable multi-part streaming to support 1 TB+ raw disk images.
3. **Wallet-Based Cryptographic Signing:** Enable MetaMask / Web3 personal signature verification so individual officers sign transactions directly with their private hardware tokens.
4. **Automated Chain Re-indexing & Consensus Monitoring:** Background daemon continuously verifying block heights and cross-referencing on-chain receipts against multiple external RPC nodes.
