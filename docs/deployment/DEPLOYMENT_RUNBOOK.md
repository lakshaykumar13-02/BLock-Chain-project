# ChainVault — Operational Deployment Runbook

**Operational Environment:** Local Demonstration & Evaluation Environment  
**Base URL:** `http://127.0.0.1:8000`  
**Web Interface:** `http://127.0.0.1:5500/login.html`  

---

## 1. Startup Sequence

Launch services strictly in the following 4-step order across separate terminal windows.

### Terminal 1: MongoDB Community Server (Windows Service)
Ensure MongoDB is running before launching backend:
```powershell
Get-Service -Name MongoDB
# If Stopped, run in Administrator PowerShell:
Start-Service -Name MongoDB
```

### Terminal 2: Hardhat Local Blockchain Node
```powershell
cd "D:\parjaayi project\CHAINVAULT\blockchain"
npx hardhat node
```
*Leave running.* Displays 20 funded accounts and `Started JSON-RPC server at http://127.0.0.1:8545/`.

*(First-time or fresh node run only — in a separate window, deploy contract:)*
```powershell
cd "D:\parjaayi project\CHAINVAULT\blockchain"
npx hardhat run scripts/deploy.js --network localhost
# Outputs contract address: 0x5FbDB2315678afecb367f032d93F642f64180aa3
```

### Terminal 3: FastAPI Backend Application
```powershell
cd "D:\parjaayi project\CHAINVAULT\backend"
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
*Expected Output:* `Uvicorn running on http://127.0.0.1:8000`.

### Terminal 4: Frontend Web Interface
```powershell
cd "D:\parjaayi project\CHAINVAULT\frontend"
python -m http.server 5500 --bind 127.0.0.1
```
*Expected Output:* `Serving HTTP on 127.0.0.1 port 5500`.

---

## 2. Health Checks & Verification URLs

| Service / Component | Verification Command / URL | Expected Response |
|---|---|---|
| **FastAPI Backend** | `curl http://127.0.0.1:8000/api/health` | `{"status": "ok", "service": "ChainVault API"}` |
| **Interactive Docs** | `http://127.0.0.1:8000/docs` | Swagger UI OpenAPI specification |
| **Blockchain Node** | `curl http://127.0.0.1:8000/api/blockchain/status` | `{"status": "online", "network": "Hardhat Local Testnet"}` |
| **Frontend UI** | `http://127.0.0.1:5500/login.html` | ChainVault Forensic Authentication Portal |
| **Dashboard** | `http://127.0.0.1:5500/dashboard.html` | 5-View Forensic Workstation Interface |

---

## 3. Synthetic Demonstration Credentials

| Role | Username | Password | Purpose |
|---|---|---|---|
| **ADMIN** | `admin` | `AdminPassword123!` | System configuration & case soft deletion |
| **INVESTIGATOR** | `investigator1` | `TestPassword123!` | Evidence ingestion & custody transfers |
| **ANALYST** | `analyst1` | `TestPassword123!` | Custody receipt & report compilation |
| **VIEWER** | `viewer1` | `TestPassword123!` | Read-only auditor examination |

---

## 4. Graceful Shutdown Sequence

1. In Terminal 4: Press `CTRL+C` to terminate Frontend HTTP server.
2. In Terminal 3: Press `CTRL+C` to terminate Uvicorn FastAPI server.
3. In Terminal 2: Press `CTRL+C` to terminate Hardhat node.
4. MongoDB Windows service remains running as background service.
