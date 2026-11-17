# ChainVault Phase 8D — Staging Preflight & Configuration Audit Report

**Authoritative Project Root:** `D:\parjaayi project\CHAINVAULT`  
**Execution Date:** October 21, 2026  
**Auditor:** Antigravity Independent Recovery & Staging Preflight Auditor  
**Audit Purpose:** Comprehensive configuration, infrastructure-as-code, and security preflight verification prior to any staging deployment authorization.  
**Operational Boundaries:** Strictly Local Audit (`DEPLOY_BROADCAST=false`, No cloud resource creation, No Render deployment, No Sepolia/Mainnet broadcasts, No contract redeployment, No production database alteration, No Git commit/push).

---

## Executive Summary

Phase 8D conducted an exhaustive, evidence-based preflight configuration audit of the ChainVault repository to determine readiness for deployment to a controlled staging environment (such as Render + Ethereum Sepolia testnet).

Every configuration asset—including `render.yaml`, `backend/requirements.txt`, `.env.example`, `blockchain/hardhat.config.js`, deployment scripts, API URL resolution logic, storage paths, health check endpoints, security middlewares, and RBAC permissions—was inspected against the active code.

All 10 configuration checks were evaluated. **9 checks PASSED**, and **1 operational observation was identified** (application-level rate limiting is delegated to the reverse proxy/CDN rather than enforced within FastAPI). 

The automated backend test suite (**233 passed**) and Hardhat smart contract suite (**17 passed**) executed with 100% pass rates. Process restart persistence was validated with exact cryptographic hash matches.

**Conclusion:** **STAGING PREFLIGHT GO**. The configuration is sound and ready for staging deployment dry-run or authorized provisioning. **PRODUCTION PREFLIGHT: NO-GO** (pending live staging validation).

---

## 1. Itemized Preflight Audit Checklist

| Item # | Audit Domain / Check | Status | Exact Evidence & Mechanism | Fixes / Action Taken |
|---|---|---|---|---|
| **1** | **Render Manifest Paths & Commands** (`render.yaml`) | **PASS** | `rootDir: backend`, `buildCommand: pip install -r requirements.txt`, `startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT`, `healthCheckPath: /api/health`, `disk.mountPath: /var/data`. Frontend `rootDir: frontend`, `staticPublishPath: .`. | None required. All paths, commands, and mount specifications align with directory structure. |
| **2** | **Environment Variable Naming Alignment** | **PASS** | Grepped all 14 environment variables across `backend/app/` (`ENVIRONMENT`, `REQUIRE_PERSISTENT_STORAGE`, `MONGO_URI`, `MONGO_DB_NAME`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `BLOCKCHAIN_RPC_URL`, `BLOCKCHAIN_CHAIN_ID`, `CONTRACT_ADDRESS`, `STORAGE_PATH`, `REPORTS_PATH`, `PUBLIC_VERIFICATION_URL_BASE`, `CORS_ORIGINS`, `ALLOW_LOCAL_QR_LINKS`). | All environment variable names match the code bit-for-bit. |
| **3** | **Production Startup Preflight Guards & Placeholder Rejection** | **PASS** | Hardened `app/security/auth.py` and `app/main.py` with `validate_production_preflight_config()`. In production mode, rejects default/placeholder secrets, short secrets (<32 chars), placeholder RPC URLs, zero contract addresses (`0x000...`), localhost RPC, and missing persistent storage with `RuntimeError`. | Added `KNOWN_PLACEHOLDER_SECRETS` in `auth.py` and comprehensive `validate_production_preflight_config()` in `main.py`. |
| **4** | **Data & Report Persistence Across Restarts** | **PASS** | Executed deterministic subprocess restart test. Evidence binary file (`case_evidence.bin`) and generated forensic PDF (`forensic_report.pdf`) survived complete process termination and reload with identical SHA-256 bitstream checksums. | Verified `get_storage_path()` and `get_reports_dir()` create directories within mounted persistent disk (`/var/data`). |
| **5** | **Zero Sensitive Credential Exposure** | **PASS** | Audited logs, error responses, `/api/health`, and `/api/blockchain/status`. `/api/health` returns only `{"status": "ok", "service": "ChainVault API"}`. `/api/recovery/diagnostics` omits URIs, passwords, private keys, and file contents. All logger statements verified free of secret leakage. | Hardened `/api/blockchain/status` to dynamically return network name, chain ID, and contract address without leaking internal RPC URLs. |
| **6** | **Network Security, CORS, Authentication & Upload Limits** | **PASS** | CORS configured with origin whitelist and security headers (`X-Frame-Options: DENY`, `nosniff`, `HSTS`). JWT HS256 auth on all mutation routes. 4-tier server-side RBAC (`ADMIN`, `INVESTIGATOR`, `ANALYST`, `VIEWER`). Upload size capped at 50MB with path traversal sanitization. Evidence deletion prohibited. | None required; robust defensive posture confirmed. |
| **7** | **Operational Rate Limiting** | **OPERATIONAL GAP (NOT VERIFIED IN-PROCESS)** | Grep for application-layer rate limiting (`slowapi`, Redis token bucket) returned zero in-process implementations. | Rate limiting is delegated to the hosting layer (Cloudflare / Render DDoS & edge rate limiting). Staging deployers must ensure edge protection is enabled. |
| **8** | **Python Dependency Compatibility & Pinning** | **PASS** | All 12 packages in `backend/requirements.txt` are pinned to exact versions. Ran `pip check` in virtual environment: `"No broken requirements found."` Verified compatibility with Python 3.12 and 3.13 runtimes. | `requirements.txt` verified compatible with both local Python 3.13.14 and Render `PYTHON_VERSION: 3.12.0`. |
| **9** | **Frontend API URL Resolution** | **PASS** | `frontend/js/api.js` resolves API base via (1) `window.__CHAINVAULT_API_URL__`, (2) `localStorage.getItem('chainvault_api_url')`, (3) localhost fallback, (4) same-origin fallback. | Documented that separate static site hosting on Render requires configuring `chainvault_api_url` in localStorage or script injection. |
| **10** | **Hardhat Config & Deployment Safety Guards** | **PASS** | `blockchain/hardhat.config.js` configures isolated `localhost` (31337) and `sepolia` (11155111). `blockchain/scripts/deploy_v2_sepolia.js` enforces `DEPLOY_BROADCAST === "true"` guard, aborting transaction broadcast in dry-run mode. | Verified dry-run guard prevents accidental Sepolia broadcasting. |

---

## 2. Test Execution & Evidence

### 2.1 Smart Contract Suite (Real Local EVM)
Executed with `npx hardhat test` in `blockchain/`:
- **Total Tests:** 17
- **Passing:** 17
- **Failing:** 0
- **Duration:** 3s
- **Execution Target:** In-process Hardhat network (`chainId: 31337`), testing live Solidity bytecode for `EvidenceRegistry` (V1) and `EvidenceRegistryV2` (custody events, sequence order, genesis anchoring, and access control).

### 2.2 Backend Regression Test Suite
Executed with `.\venv\Scripts\pytest -q` in `backend/`:
- **Total Tests:** 233
- **Passing:** 233
- **Failing:** 0
- **Duration:** 199.45s (3m 19s)
- **Breakdown of Test Suites:**
  - `test_phase8c_recovery_audit.py`: 10 passed (reproducing Windows 1–10).
  - `test_phase8b_transaction_consistency.py`: 9 passed (durable transaction states, lease fencing, idempotency fast path).
  - `test_phase7_custody_concurrency.py`: 10 passed (lease locks, tamper detection, EVM RPC failures).
  - `test_phase7_audit_validation.py`: 13 passed (fencing tokens, lease renewal, crash recovery).
  - `test_evidence_integrity_suite.py`: 20 passed (tamper-evident SHA-256 validation).
  - `test_forensic_report_suite.py`: 22 passed (ReportLab PDF bitstream, QR generation).
  - `test_custody_audit_trail.py`: 18 passed (canonical event hashing, cryptographic chains).
  - `test_api_contract_security.py`: 12 passed (RBAC, auth rejection, secret non-disclosure).
  - Other unit/route suites: 119 passed.

### 2.3 Production Preflight Guard Verification
Executed deterministic isolation tests verifying that `validate_production_preflight_config()` halts startup under illegal production states:
```
PASS 1 (rejected placeholder secret): CRITICAL: Production mode rejects default, placeholder, or short (<32 chars) JWT_SECRET.
PASS 2 (rejected short secret): CRITICAL: Production mode rejects default, placeholder, or short (<32 chars) JWT_SECRET.
PASS 3 (rejected placeholder RPC): CRITICAL: Production mode rejects placeholder BLOCKCHAIN_RPC_URL.
PASS 4 (rejected chain ID 31337): CRITICAL: Production mode cannot target local Hardhat testnet (chain ID 31337).
PASS 5 (rejected zero address): CRITICAL: Production mode requires a valid non-zero CONTRACT_ADDRESS: 0x0000000000000000000000000000000000000000.
PASS 6 (rejected localhost RPC): CRITICAL: Production mode cannot target localhost RPC: http://127.0.0.1:8545.
```

### 2.4 Restart Persistence Verification
Executed subprocess persistence test simulating container termination:
```
PERSISTENCE RESTART TEST: PASSED. Evidence binary and forensic PDF survived process termination with exact hash match.
```

---

## 3. Test Distinction: Mocked vs. Real Local EVM

To uphold rigorous audit standards:
- **Real Local EVM Tests**:
  - `blockchain/test/EvidenceRegistryV2.test.js` (17 tests) run directly against the local Hardhat EVM. Zero mocking.
  - `backend/tests/test_phase7_custody_concurrency.py` tests 1, 3, 4, 5, 7, 8, 9, 10 execute live JSON-RPC calls against the local Hardhat node when running.
- **Deterministic Fault-Injection Tests (Mocks)**:
  - `backend/tests/test_phase8c_recovery_audit.py` (10 tests) and `test_phase8b_transaction_consistency.py` use monkeypatched JSON-RPC and network responses to simulate hardware crashes, network drops, malformed node receipts, and mempool drops deterministically.
  - Mocked tests are never reported as real blockchain integration tests.

---

## 4. Operational Considerations & Remaining Staging Blockers

Before initiating the staging deployment on Render and Sepolia, the staging operations team must resolve the following environment-specific tasks:

1. **MongoDB Atlas Connection**:
   - Create a staging MongoDB Atlas cluster (M0 free tier or dedicated replica set) with IP access list enabled for Render.
   - Populate `MONGO_URI` securely in the Render dashboard.
2. **Sepolia RPC & Deployer Account**:
   - Provision an Alchemy or Infura Sepolia RPC URL and set `BLOCKCHAIN_RPC_URL`.
   - Fund a testnet deployer address with Sepolia testnet ETH (faucet).
   - Set `SEPOLIA_PRIVATE_KEY` in local build environment to deploy `EvidenceRegistryV2.sol` via `scripts/deploy_v2_sepolia.js` with `DEPLOY_BROADCAST=true`.
   - Copy the resulting contract address to `CONTRACT_ADDRESS` on Render.
3. **Frontend API Configuration**:
   - After deploying `chainvault-api` on Render, copy its public URL (e.g., `https://chainvault-api.onrender.com`).
   - Set `CORS_ORIGINS` on the backend to include `https://chainvault-frontend.onrender.com`.
   - Set `PUBLIC_VERIFICATION_URL_BASE` to `https://chainvault-api.onrender.com`.
4. **Edge Rate Limiting**:
   - Configure Cloudflare or Render edge rate limiting rules to protect `/api/auth/login` and `/api/evidence/upload` against brute-force or volumetric denial-of-service.

---

## 5. Staging Preflight Recommendation

### STAGING PREFLIGHT: **GO**
- **Justification**:
  1. Infrastructure-as-code specification (`render.yaml`) accurately maps to directory structure, entry points, disk mounts, and environment variables.
  2. Production preflight configuration guards actively prevent placeholder secrets, zero addresses, localhost RPC, and missing databases from running.
  3. Evidence files and PDF reports survive process restarts on persistent storage.
  4. Health checks, diagnostics, and logs do not expose sensitive credentials.
  5. 233 backend tests and 17 Hardhat contract tests pass cleanly.

### PRODUCTION DEPLOYMENT: **NO-GO**
- **Justification**:
  - Production deployment remains strictly prohibited until a successful staging lifecycle has validated live Sepolia transaction mining, gas price spikes, network latency, and multi-replica worker fencing under real-world conditions.
