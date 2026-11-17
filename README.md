# ChainVault
Blockchain-Based Digital Evidence Integrity & Chain-of-Custody Platform.

## Problem Statement
Maintaining the integrity of digital evidence is crucial in forensics. Standard storage methods can be tampered with.

## Core Concept
ChainVault securely stores evidence metadata and cryptographic hashes on a blockchain while keeping the large evidence files in a secure local or distributed storage system. This ensures a tamper-proof chain of custody.

## Architecture Overview
- **Frontend**: HTML5, CSS3, Vanilla JavaScript (Single-Page Application)
- **Backend**: Python 3.11+, FastAPI, Uvicorn (Dual-adapter database engine)
- **Database**:
  - **Primary Staging**: Google Cloud Firestore (`chainvault-staging`, `(default)` database via ADC)
  - **Authoritative Rollback Source**: Local MongoDB (`mongodb://localhost:27017/chainvault`)
- **Blockchain**: Solidity (`EvidenceRegistryV2`), Hardhat local node / Ethereum Sepolia Testnet

---

## Environment Configuration

Configuration is loaded from `.env` in the project root (or `backend/.env`).

```env
# Database Backend Configuration
ENVIRONMENT=staging
REQUIRE_PERSISTENT_STORAGE=true
DATABASE_BACKEND=firestore

# Google Cloud Firestore (Staging)
FIREBASE_PROJECT_ID=chainvault-staging
FIRESTORE_DATABASE_ID=(default)

# MongoDB (Authoritative Rollback Source)
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=chainvault

# Authentication & Security
JWT_SECRET=super_secret_jwt_key_chainvault_staging_32_chars_long
JWT_EXPIRE_MINUTES=60
# In production, set non-default initial passwords via:
# ADMIN_INITIAL_PASSWORD=YourStrongAdminPasswordHere!
# INVESTIGATOR_INITIAL_PASSWORD=YourStrongInvestigatorPasswordHere!

# Blockchain Configuration (Active Local Development)
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
BLOCKCHAIN_CHAIN_ID=31337
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3

# Production Blockchain Configuration (Sepolia or Dedicated EVM)
# BLOCKCHAIN_RPC_URL=https://sepolia.infura.io/v3/<REAL_PROJECT_KEY>
# BLOCKCHAIN_CHAIN_ID=11155111
# CONTRACT_ADDRESS=0x<DEPLOYED_CONTRACT_ADDRESS>
```

---

## Verified Startup Order & Exact Commands

Start services in the following order:

### 1. Blockchain Ledger Node (Local Development)
```powershell
cd blockchain
npx hardhat node --hostname 127.0.0.1 --port 8545
```
* **Status**: JSON-RPC server listening at `http://127.0.0.1:8545` (Chain ID: `31337`).
* Contract deployment: `npx hardhat run scripts/deploy.js --network localhost` (deploys `EvidenceRegistry` to `0x5FbDB2315678afecb367f032d93F642f64180aa3`).

### 2. Backend Service (FastAPI)
Run from the project root in PowerShell:
```powershell
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
* **Status**: Running on `http://127.0.0.1:8000`
* **Health Endpoint**: `http://127.0.0.1:8000/api/health`
* **OpenAPI Documentation**: `http://127.0.0.1:8000/docs`

### 3. Frontend Application (Static HTTP Server)
Run from the project root in a second terminal:
```powershell
python -m http.server 5500 --directory frontend
```
* **Landing Page**: `http://127.0.0.1:5500/index.html`
* **Login URL**: `http://127.0.0.1:5500/login.html`
* **Super Admin Portal**: `http://127.0.0.1:5500/superadmin.html`
* **Investigator & Admin Dashboard**: `http://127.0.0.1:5500/dashboard.html`
* **Employee / Officer Portal**: `http://127.0.0.1:5500/employee.html`
* **Development Super Admin Credentials**: `superadmin` / `SuperAdminDev2026!` (Role: `SUPER_ADMIN`)
* **Default Admin Credentials**: `admin` / `AdminPassword123!` (Role: `ADMIN`)
* **Default Investigator Credentials**: `investigator1` / `TestPassword123!` (Role: `INVESTIGATOR`)
* **Default Employee Credentials**: `employee1` / `EmployeePassword123!` (Role: `EMPLOYEE`)

---

## Security Architecture & Production Guardrails

ChainVault incorporates defense-in-depth security controls across its application layers:

1. **Authentication & Password Security**:
   * Cryptographic password storage using `bcrypt` salted hashes.
   * Signed JWT session tokens with strict algorithm enforcement (`HS256`) and expiration checking.
   * In-memory sliding-window login rate limiting (5 consecutive failures per IP or username within 60s triggers `HTTP 429 Too Many Requests`).
2. **Authorization & Role-Based Access Control (RBAC)**:
   * Server-side route authorization via `require_role(...)`.
   * Unprivileged or unauthorized requests reject with `HTTP 401 Unauthorized` or `HTTP 403 Forbidden`.
   * Dangerous operations (such as case soft-deletion and consistency audit reports) are strictly restricted to `ADMIN`.
3. **HTTP & Network Defenses**:
   * Defensive security headers on all responses: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, and `Referrer-Policy`.
   * Strict origin filtering via `CORS_ORIGINS`.
4. **Evidence Storage & Forensic Integrity**:
   * Storage path traversal protection: Null-byte checks, directory traversal sequence rejection (`..`, `/`, `\`), and canonical path root confinement.
   * 50MB file size upload limit and SHA-256 integrity digest validation.
   * Tripartite verification comparing physical disk bytes, Firestore metadata, and smart contract ledger state.
5. **Production Preflight Validation (`app/main.py`)**:
   * When `ENVIRONMENT=production`, the application refuses startup if placeholder `JWT_SECRET`, default admin credentials, local RPC URLs, unwritable storage directories, active emulator hosts, non-HTTPS verification URLs, or wildcard CORS origins are detected.
6. **Proxy Spoofing Defense (`TRUSTED_PROXIES`)**:
   * `X-Forwarded-For` headers are only trusted if the connecting peer IP matches `TRUSTED_PROXIES` (default `127.0.0.1,::1`), preventing rate limit bypasses.

---

## Migration, Backups & Rollback

* **Pre-Migration MongoDB Backup**: [`backend/backups/mongodb_backup_pre_migration_20261024/`](backend/backups/mongodb_backup_pre_migration_20261024/)
  * Complete BSON/JSON dumps of all collections with SHA-256 integrity manifest.
* **Live Cloud Migration Manifest**: [`backend/backups/live_cloud_migration_manifest.json`](backend/backups/live_cloud_migration_manifest.json)
  * Records all 6 migrated records (audit_logs, evidence, blockchain_checkpoints) to Cloud Firestore with zero errors.
* **Firestore Automated Backup & Recovery**:
  * Export: `gcloud firestore export gs://<backup-bucket>/$(date +%Y%m%d_%H%M%S)`
  * Restore: `gcloud firestore import gs://<backup-bucket>/<timestamp>/`
* **Instant Rollback**: To revert backend operation to local MongoDB at any time, switch the database engine in `.env`:
  ```env
  DATABASE_BACKEND=mongodb
  ```
  and restart the backend. Local MongoDB data on `localhost:27017` remains fully intact.

---

## Production Deployment Guide

For complete hosting topology, reverse proxy configuration (Nginx), persistent storage volume mounting, Firestore IAM least-privilege setup, and blockchain network selection (Sepolia vs Polygon vs Besu), see the [Production Deployment Plan](docs/deployment/PRODUCTION_DEPLOYMENT_PLAN.md).
