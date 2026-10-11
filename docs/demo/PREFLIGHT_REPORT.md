# ChainVault — Phase 13.1 Preflight & Environment Verification Report

**Verification Date:** 2026-10-11  
**Project Root:** `C:\ChainVault` (Local Workspace: `d:\parjaayi project\CHAINVAULT`)  
**Phase:** Phase 13.1 (Preflight & Environment Verification)  
**Overall Preflight Status:** **READY FOR DEMONSTRATION — ALL SERVICES LIVE**  

---

## 1. Verified Environment & Tool Versions

| Runtime / Tool | Detected Version | Command | Status |
|---|---|---|:---:|
| **Python** | `3.13.14` | `python.exe --version` | Verified Active |
| **Node.js** | `v22.20.0` | `node.exe --version` | Verified Active |
| **npm** | `10.9.3` | `npm.cmd --version` | Verified Active |
| **Hardhat** | `2.29.1` | `npx.cmd hardhat --version` | Verified Active |
| **Git** | `2.55.0.windows.3` | `git.exe --version` | Verified Active |
| **Pytest** | `9.1.1` | `.\venv\Scripts\pytest.exe --version` | Verified Active |
| **MongoDB Service** | Community Server | `Get-Service -Name MongoDB` | Verified Active (Running) |

---

## 2. Local Services Verification & Startup Matrix

All 4 local services were verified and launched in dependency order using the project's documented commands:

| Service | Configured Endpoint & Port | Startup Command Used | Execution Result | Health-Check Probe & Verified Output | Service Status |
|---|---|---|---|---|:---:|
| **MongoDB Community Server** | `mongodb://localhost:27017`<br>Target DB: `chainvault`<br>Test DB: `chainvault_test` | Windows Service `MongoDB`<br>(Managed via SCM) | Succeeded (Service Running) | TCP port 27017 active (`TcpTestSucceeded: True`); Motor ping `admin.command('ping')` -> `pong.ok == 1.0` | **HEALTHY** |
| **Hardhat Standalone Node** | `http://127.0.0.1:8545`<br>Chain ID: `31337`<br>Contract: `0x5FbDB...` | `npx hardhat node`<br>(Background daemon) | Succeeded (Block height: 85+) | JSON-RPC `net_version` -> `31337`; Contract `EvidenceRegistry.sol` active at `0x5FbDB2315678afecb367f032d93F642f64180aa3` | **HEALTHY** |
| **FastAPI Backend Application** | `http://127.0.0.1:8000`<br>Prefix: `/api` | `.\venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000`<br>(Background daemon) | Succeeded (Uvicorn running) | `GET /api/health` -> HTTP 200 `{"status":"ok","service":"ChainVault API"}`<br>`GET /api/blockchain/status` -> HTTP 200 `{"status":"online"}` | **HEALTHY** |
| **Frontend Web Interface** | `http://127.0.0.1:5500`<br>API Base: `http://localhost:8000/api` | `python -m http.server 5500 --bind 127.0.0.1`<br>(Background daemon) | Succeeded (HTTP server running) | `GET /login.html` -> HTTP 200<br>`GET /index.html` -> HTTP 200<br>Frontend points to authorized port in CORS | **HEALTHY** |

---

## 3. End-to-End Live API Smoke Test

A live, unmocked roundtrip was performed against the running FastAPI daemon and MongoDB/Blockchain backend:
1. `GET /api/health`: Returned HTTP 200 with `service: "ChainVault API"`.
2. `GET /api/blockchain/status`: Returned HTTP 200 with `status: "online"`, confirming live connection from FastAPI to the Hardhat node on port 8545.
3. `POST /api/auth/login`: Authenticated `investigator1` using bcrypt verification, issuing a valid JWT access token.
4. `GET /api/cases`: Authenticated with `Bearer <token>`, successfully returning active cases list.

---

## 4. Security, Safety & Secret Handling Verification

- **Secrets Handling:** Checked `.env.example` vs `.gitignore`. Confirmed `.env` and private keys are excluded from git tracking.
- **Client Security:** Frontend JavaScript assets (`frontend/js/`) do not contain private keys, seed phrases, or database connection strings.
- **Network Isolation:** All services are bound strictly to local loopback addresses (`127.0.0.1` / `localhost`). Zero external or public network exposure.
- **Data Protection:** Existing evidence in `storage/evidence` and active MongoDB database `chainvault` remain untouched. Demonstration workflows use isolated synthetic records.
- **Automated Safeguards:** Destructive drop commands on development database `chainvault` remain blocked by `MongoDBClient.safeguard_test_database()`.

---

## 5. Checkpoint & Recovery Verification Summary

- **Latest Stable Checkpoint:** `e54d43e` / `26d3c83`
- **Recovery Verification Procedure:** Documented in [RECOVERY_LOG.md](file:///d:/parjaayi%20project/CHAINVAULT/docs/RECOVERY_LOG.md)
  - Target Path: `d:\parjaayi project\ChainVault-recovery-test`
  - Restored Files: 84 / 84 tracked files matched repository manifest.
  - Secret Check: Confirmed `.env` and sensitive files were not committed or restored (`Has .env leaked: False`).
  - Isolated Import Test: `python -c "import app.main; print('Isolated recovery backend import OK')"` -> **Passed (Exit Code: 0)**.
  - Result: **Proven Recovery Point Verified**.

---

## 6. Known Blockers, Exceptions & Limitations

- **Active Blockers:** **0** (Zero blocking defects exist).
- **Network Scope:** Strict local development environment. Public testnets and mainnets are excluded by design for this phase.
- **Demonstration Scope:** Workflows will execute against the confirmed local services using synthetic forensic assets.

---

## 7. Next Action

Proceed to **Phase 13.2: Complete Demonstration Execution**:
1. Execute full interactive demonstration through the web interface and API.
2. Demonstrate complete evidence lifecycle: login, case creation, synthetic evidence upload, SHA-256 verification, on-chain registration, custody transfer, tripartite hash verification, QR badge generation, and signed forensic PDF generation.
