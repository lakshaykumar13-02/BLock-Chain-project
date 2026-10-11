# ChainVault — Demonstration Runbook & Operational Guide

**System Location:** `d:\parjaayi project\CHAINVAULT`  
**Purpose:** Standard Operating Procedure (SOP) for setting up, starting, verifying, demonstrating, and shutting down the ChainVault platform in a clean local environment.  
**Verified Checkpoint:** `b3c85c0` (Phase 13.2 Complete)

---

## 1. Environment Prerequisites

Before initiating platform services, verify the following installed tools on the host system:

| Component | Minimum Version | Verification Command | Purpose |
|---|---|---|---|
| **Python** | 3.11+ (Detected: 3.13.14) | `python.exe --version` | FastAPI backend, cryptographic hashing, PDF generation |
| **Node.js** | 20 LTS+ (Detected: v22.20.0) | `node.exe --version` | Hardhat Ethereum development environment |
| **npm** | 10+ (Detected: 10.9.3) | `npm.cmd --version` | Node package manager |
| **Hardhat** | 2.29+ (Detected: 2.29.1) | `npx.cmd hardhat --version` | Local blockchain EVM node & Solidity compiler |
| **MongoDB** | Community Server 7.0+ | `Get-Service -Name MongoDB` | Document store for case & evidence metadata |
| **Git** | 2.40+ (Detected: 2.55.0) | `git.exe --version` | Version control & checkpoint provenance |

---

## 2. Platform Parameters & Health-Check Directory

| Parameter / Service | Configured Value | Health Check Endpoint / Probe |
|---|---|---|
| **Hardhat JSON-RPC Endpoint** | `http://127.0.0.1:8545` | `curl -X POST http://127.0.0.1:8545 -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"net_version","params":[],"id":1}'` |
| **Hardhat Network Chain ID** | `31337` | Returns `"31337"` |
| **Deployed Smart Contract** | `0x5FbDB2315678afecb367f032d93F642f64180aa3` | `GET http://127.0.0.1:8000/api/blockchain/status` |
| **MongoDB Connection URI** | `mongodb://localhost:27017` | `Test-NetConnection -ComputerName 127.0.0.1 -Port 27017` |
| **Application Database** | `chainvault` | Default development database |
| **Automated Test Database** | `chainvault_test` | Strictly enforced by automated safeguards |
| **FastAPI Backend Server** | `http://127.0.0.1:8000` | `GET http://127.0.0.1:8000/api/health` (Returns `{"status": "ok"}`) |
| **FastAPI Interactive Docs** | `http://127.0.0.1:8000/docs` | Swagger UI OpenAPI specification |
| **Frontend Web Server** | `http://127.0.0.1:5500` | `http://127.0.0.1:5500/login.html` and `dashboard.html` |
| **QR Code Verification URI** | `http://localhost:8000/api/verification/verify?evidence_id={id}` | Encoded by `GET /api/reports/qr/{id}` (Note: Resolves locally on host PC; external mobile scanning requires configuring a LAN IP) |

---

## 3. Strict Service Startup Order

Services must be launched in their precise dependency order to ensure uninterrupted connectivity across architectural tiers.

### Step 1: MongoDB Community Server (Windows Service)
MongoDB must be active before starting the backend application:
```powershell
# Check Windows Service status
Get-Service -Name MongoDB

# If service is stopped, start it via PowerShell (Administrator):
Start-Service -Name MongoDB

# Verify TCP socket is listening on port 27017
Test-NetConnection -ComputerName 127.0.0.1 -Port 27017
```

### Step 2: Local Hardhat Blockchain Node (Terminal 1)
Start the standalone EVM JSON-RPC daemon:
```powershell
cd "d:\parjaayi project\CHAINVAULT\blockchain"
npx hardhat node
```
*Expected Output:*
- List of 20 funded test accounts with private keys.
- `Started HTTP and WebSocket JSON-RPC server at http://127.0.0.1:8545/`
- Leave this terminal running as a dedicated daemon.

*(Note: If the contract is not yet deployed on this fresh node run, deploy it in a separate window:)*
```powershell
cd "d:\parjaayi project\CHAINVAULT\blockchain"
npx hardhat run scripts/deploy.js --network localhost
# Outputs deployed address: 0x5FbDB2315678afecb367f032d93F642f64180aa3
```

### Step 3: FastAPI Backend Application (Terminal 2)
Activate the Python virtual environment and launch Uvicorn:
```powershell
cd "d:\parjaayi project\CHAINVAULT\backend"
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
*Expected Output:*
- `INFO: Started server process`
- `INFO: Waiting for application startup`
- `INFO: Successfully connected to MongoDB.` (or resilient in-memory notice if offline)
- `INFO: Uvicorn running on http://127.0.0.1:8000`

### Step 4: Frontend Web Interface (Terminal 3)
Serve the static web assets on the pre-authorized CORS port 5500:
```powershell
cd "d:\parjaayi project\CHAINVAULT\frontend"
python -m http.server 5500 --bind 127.0.0.1
```
*Expected Output:*
- `Serving HTTP on 127.0.0.1 port 5500 (http://127.0.0.1:5500/) ...`

---

## 4. Synthetic Demonstration Accounts

For security, the application uses preconfigured demonstration accounts with bcrypt-hashed credentials. Demonstration credentials follow standard forensic test conventions:

| Username / Badge ID | User Role | Permitted Actions | Demonstration Use Case |
|---|---|---|---|
| `admin` | `ADMIN` | User administration, case soft-deletion, audit queries | System administrator / Evidence repository manager |
| `investigator1` | `INVESTIGATOR` | Case creation, evidence upload, blockchain anchoring, custody transfer | Primary demonstrator account |
| `analyst1` | `ANALYST` | Evidence analysis, tripartite verification, custody recipient | Forensics lab analyst for custody transfer |
| `viewer1` | `VIEWER` | Read-only inspection of cases and evidence | Demonstrating HTTP 403 Forbidden rejection on mutations |
| `suspended_user` | `VIEWER` (Inactive) | None (`is_active: false`) | Demonstrating HTTP 403 Forbidden rejection on inactive login |

*(Note: Actual demonstration credentials are documented in secure team configuration and never committed to version control.)*

---

## 5. System Shutdown Procedure

To cleanly terminate demonstration services without corrupting state:

1. **Terminal 3 (Frontend):** Press `Ctrl + C` to stop the Python HTTP server.
2. **Terminal 2 (FastAPI):** Press `Ctrl + C` to trigger the graceful lifespan shutdown:
   - `INFO: Shutting down`
   - `INFO: MongoDB connection closed.`
   - `INFO: Finished server process`
3. **Terminal 1 (Hardhat Node):** Press `Ctrl + C` to stop the local blockchain daemon.
4. **MongoDB Service:** Windows service can remain running in background or stopped via `Stop-Service -Name MongoDB`.
5. **Background Task Cleanup (If launched via IDE/CLI):**
   ```powershell
   # Stop any background python or node daemons if necessary
   Get-Process -Name python, node, uvicorn -ErrorAction SilentlyContinue
   ```

---

## 6. Comprehensive Troubleshooting Guide

### A. MongoDB Community Server Issues
- **Symptom:** `Could not connect to MongoDB: ServerSelectionTimeoutError`.
- **Diagnosis:** The local MongoDB service is either stopped or port 27017 is blocked.
- **Resolution:**
  1. Open PowerShell as Administrator and run: `Get-Service -Name MongoDB`.
  2. If status is `Stopped`, execute: `Start-Service -Name MongoDB`.
  3. Verify port reachability: `Test-NetConnection -ComputerName 127.0.0.1 -Port 27017`.
  4. *Note on In-Memory Fallback vs. Durable Storage:* The ChainVault backend incorporates an automatic fallback store (`CASES_STORE`, `EVIDENCE_STORE`, `AUDIT_LOGS_STORE`), allowing demonstration continuation if MongoDB is temporarily unavailable. However, in-memory data resides purely in Python process RAM and is lost upon restarting Uvicorn. Keep the MongoDB service running for durable, persistent storage across server restarts.

### B. Hardhat Node & Blockchain Issues
- **Symptom:** `/api/blockchain/status` reports `"status": "offline"`.
- **Diagnosis:** Hardhat node process was terminated or restarted with a different chain ID.
- **Resolution:**
  1. Verify port 8545: `Test-NetConnection -ComputerName 127.0.0.1 -Port 8545`.
  2. If inactive, launch `npx hardhat node` in `blockchain/`.
  3. Re-deploy `EvidenceRegistry.sol` using `npx hardhat run scripts/deploy.js --network localhost`.
  4. Ensure `CONTRACT_ADDRESS` in `.env` matches the newly deployed address.
  5. *Note on Local Chain State:* Hardhat is an ephemeral local EVM node. Restarting the node resets the blockchain state to Genesis (Block 0), discarding previous transaction history and requiring contract redeployment. Illustrative transaction hashes and block numbers in documentation reflect the active node session.

### C. FastAPI Backend Startup Errors
- **Symptom:** `Error: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): address already in use`.
- **Diagnosis:** An earlier Uvicorn instance is still holding port 8000.
- **Resolution:**
  1. Identify the process ID holding port 8000:
     ```powershell
     Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
     ```
  2. Terminate the blocking process: `Stop-Process -Id <PID> -Force`.
  3. Restart Uvicorn.

### D. Frontend CORS Rejection
- **Symptom:** Browser console logs: `Access to fetch at 'http://localhost:8000/api/...' has been blocked by CORS policy`.
- **Diagnosis:** The frontend is being served on an unauthorized port (e.g., port 8081 or 5000).
- **Resolution:**
  1. Ensure the Python HTTP server was started with: `python -m http.server 5500 --bind 127.0.0.1`.
  2. Authorized ports configured in `backend/app/main.py` are: `5500`, `8080`, and `3000`. Port 5500 is the designated default.

### E. Evidence Upload "File Too Large" (HTTP 413)
- **Symptom:** `POST /api/evidence/upload` returns `HTTP 413 Payload Too Large`.
- **Diagnosis:** File exceeds the 50 MB security threshold configured in `evidence.py`.
- **Resolution:** Use synthetic forensic disk images or test payloads under 50 MB for live demonstration purposes.
