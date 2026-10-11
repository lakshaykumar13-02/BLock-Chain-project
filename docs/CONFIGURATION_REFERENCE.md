# CONFIGURATION REFERENCE

This document details all configuration parameters, environment variables, default ports, and service endpoints for the ChainVault platform in accordance with the **Environment & Configuration Management Policy** (`docs/ENVIRONMENT_CONFIGURATION_POLICY.md`).

---

## 1. Authoritative Ports & Service Endpoints

| Service | Protocol / Host | Default Port | Base URL / RPC Endpoint | Purpose |
|---|---|---|---|---|
| **Frontend** | HTTP / localhost | `5500` | `http://127.0.0.1:5500` | Static Web Interface (HTML/CSS/JS) |
| **FastAPI Backend** | HTTP / localhost | `8000` | `http://127.0.0.1:8000` (`/api`) | Core REST API & Business Logic |
| **Hardhat Blockchain** | JSON-RPC / localhost | `8545` | `http://127.0.0.1:8545` | Local Ethereum Development Node |
| **MongoDB (Dev)** | MongoDB Protocol | `27017` | `mongodb://localhost:27017/chainvault` | Primary Evidence & Custody Store |
| **MongoDB (Test)** | MongoDB Protocol | `27017` | `mongodb://localhost:27017/chainvault_test` | Dedicated Test Database (Isolated) |

---

## 2. Environment Variables Matrix

| Variable Name | Purpose | Status | Safe Example / Default | Consuming Component | Environment | Change Action Required |
|---|---|---|---|---|---|---|
| `MONGO_URI` | Connection URI for the MongoDB instance | Required | `mongodb://localhost:27017` | `backend/app/database/mongodb.py` | Local Dev / Automated Testing | Requires Backend restart |
| `MONGO_DB_NAME` | Target database name for application storage | Required | `chainvault` (Dev) / `chainvault_test` (Test) | `backend/app/database/mongodb.py` | Local Dev / Automated Testing | Requires Backend restart; triggers new DB creation |
| `JWT_SECRET` | Cryptographic secret for signing and verifying authentication tokens | Required | `your_super_secret_key_change_in_production` *(Placeholder only)* | `backend/app/security/` | Local Dev / Testing / Demo | Requires Backend restart; invalidates existing sessions |
| `JWT_EXPIRE_MINUTES` | Lifetime of issued authentication tokens | Optional | `30` | `backend/app/security/` | Local Dev / Automated Testing | Requires Backend restart |
| `BLOCKCHAIN_RPC_URL` | JSON-RPC endpoint for smart contract interactions | Required | `http://127.0.0.1:8545` | `backend/app/services/blockchain.py`, Hardhat scripts | Local Dev / Automated Testing | Requires Backend restart |
| `CONTRACT_ADDRESS` | Deployed address of `EvidenceRegistry.sol` | Required *(Post-deploy)* | `0x5FbDB2315678afecb367f032d93F642f64180aa3` *(Local Hardhat default)* | `backend/app/services/blockchain.py` | Local Dev / Automated Testing / Demo | Requires Contract redeployment & Backend restart |
| `STORAGE_PATH` | File system location for physical evidence files | Required | `storage/evidence` | `backend/app/services/storage.py` | Local Dev / Automated Testing | Requires Backend restart; directory creation |

---

## 3. Environment Separation Guidelines

1. **Local Development:**
   - Active database: `chainvault`
   - Blockchain: Local Hardhat Node (`http://127.0.0.1:8545`)
   - Configuration read from: `.env` (derived from `.env.example`, not committed)

2. **Automated Testing:**
   - Active database: strictly isolated to `chainvault_test`
   - Test suites must never mutate the development `chainvault` database or production storage paths.
   - Evidence files created during tests must be saved in temporary fixtures and removed upon teardown.

3. **Demonstration Environment:**
   - Uses pre-seeded, sanitized demonstration cases and verified smart contract deployments on local Hardhat.
   - Secrets must remain in local environment variables, never hardcoded in scripts or UI presentations.

---

## 4. Secrets Security Rules

- **Zero Hardcoded Credentials:** Never store plaintext passwords, private keys, or actual signing secrets in source files or Git.
- **Git Ignore Enforcement:** `.env` is explicitly ignored by `.gitignore`.
- **Secret Exposure Protocol:** If a secret is committed or leaked:
  1. Immediately stop current execution.
  2. Notify the Project Owner.
  3. Rotate all affected secrets and keys immediately.
  4. Purge sensitive values from Git history using an approved, isolated procedure.
