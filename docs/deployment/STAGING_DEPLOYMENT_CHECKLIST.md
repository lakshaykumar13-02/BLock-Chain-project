# ChainVault Staging Deployment Checklist & Operations Guide

**Scope:** Public Staging Deployment Preparation  
**Target Platform:** Render (FastAPI Web Service + Static Site + Persistent Disk)  
**Target Blockchain:** Ethereum Sepolia Testnet (Chain ID `11155111`)  
**Primary Database:** Google Cloud Firestore (`chainvault-staging`)  
**Authoritative Rollback Source:** MongoDB (Local / Atlas Replica Set)  
**Smart Contract:** `EvidenceRegistryV2.sol`  

---

## 1. Pre-Deployment Authorization & Security Boundaries

Prior to executing any live deployment actions, verify explicit user authorization for:
- [ ] Incurring cloud resource costs (Render Standard/Starter Plan required for Persistent Disk).
- [ ] Uploading Google Cloud Service Account credentials to Render Secret Files.
- [ ] Funding an isolated Sepolia testnet deployer address with faucet ETH.
- [ ] Broadcasting on-chain contract deployment transaction via Hardhat.
- [ ] Pushing project code to a public/private remote Git repository connected to Render.

> [!WARNING]
> NEVER commit `.env` containing live secrets, private keys, or credentials to Git. Always inject configuration directly into the Render Dashboard or as a Render Secret File.

---

## 2. Infrastructure Provisioning Checklist

### 2.1 Primary Database: Google Cloud Firestore
1. [ ] Confirm Google Cloud Project: `chainvault-staging` (Database: `(default)`).
2. [ ] Generate a dedicated Service Account with least-privilege role:
   - Role: `Cloud Datastore User` (`roles/datastore.user`).
3. [ ] Create and download the JSON keyfile: `gcp-service-account.json`.
4. [ ] In Render Dashboard for `chainvault-api`:
   - Navigate to **Environment** $\rightarrow$ **Secret Files**.
   - Filename: `/etc/secrets/gcp-service-account.json`.
   - Content: Paste the contents of `gcp-service-account.json`.
5. [ ] Authoritative Rollback Preservation:
   - Ensure existing local MongoDB backups in `backend/backups/mongodb_backup_pre_migration_20261024/` and `live_cloud_migration_manifest.json` remain preserved and unmodified.

### 2.2 Blockchain: Ethereum Sepolia Testnet
1. [ ] **Obtain Sepolia Test ETH:**
   - Create or designate an isolated deployer address (never reuse an account containing mainnet funds).
   - Acquire ~0.05 – 0.1 Sepolia test ETH using official faucets:
     - Google Cloud Web3 Faucet: `https://cloud.google.com/application/web3/faucet/ethereum/sepolia`
     - Alchemy Sepolia Faucet: `https://www.alchemy.com/faucets/ethereum-sepolia`
     - Infura Sepolia Faucet: `https://www.infura.io/faucet/sepolia`
     - QuickNode Sepolia Faucet: `https://faucet.quicknode.com/ethereum/sepolia`
     - Sepolia PoW Faucet: `https://sepolia-faucet.pk910.de/`
2. [ ] **Configure Sepolia RPC Provider:**
   - Register for an RPC provider (Alchemy, Infura, or QuickNode).
   - Create an Ethereum Sepolia app and copy the HTTPS RPC endpoint:
     - Infura format: `https://sepolia.infura.io/v3/<PROJECT_ID>`
     - Alchemy format: `https://eth-sepolia.g.alchemy.com/v2/<API_KEY>`
3. [ ] **Execute Local Dry-Run Check (Zero Gas, No Broadcast):**
   ```bash
   cd blockchain
   npx hardhat run scripts/deploy_v2_sepolia.js
   ```
   *Expected Output: "SAFETY GUARD ACTIVE: DEPLOY_BROADCAST is not set to 'true'. Dry-run validation successful. No transactions were broadcast."*
4. [ ] **Execute Live Sepolia Deployment (Requires Explicit User Authorization):**
   ```powershell
   cd blockchain
   $env:DEPLOY_BROADCAST="true"
   $env:SEPOLIA_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/<API_KEY>"
   $env:SEPOLIA_PRIVATE_KEY="<64_HEX_CHAR_PRIVATE_KEY_WITHOUT_0X>"
   npx hardhat run scripts/deploy_v2_sepolia.js --network sepolia
   ```
5. [ ] **Record Deployment Artifacts:**
   - The deployment script automatically saves public data to:
     `blockchain/deployments/sepolia_EvidenceRegistryV2.json`
   - Contains: `contractName`, `address`, `network`, `chainId: 11155111`, `deployer`, `transactionHash`, and `abi`.
   - Never exposes private keys or RPC credentials.
   - Preserves local deployment file `blockchain/deployments/localhost_EvidenceRegistry.json`.
6. [ ] *(Optional)* Verify contract on Sepolia Etherscan:
   ```bash
   npx hardhat verify --network sepolia <DEPLOYED_CONTRACT_ADDRESS>
   ```

### 2.3 Render Services (Blueprint Provisioning via `render.yaml`)
1. [ ] Connect the Git repository to Render using **New Blueprint Instance**.
2. [ ] Review the auto-detected services in `render.yaml`:
   - **`chainvault-api`** (Web Service, Python 3.12, plan: `standard`).
   - **`chainvault-storage`** (Persistent Disk mounted at `/var/data`, 10GB).
   - **`chainvault-frontend`** (Static Site, root directory: `frontend`).
3. [ ] Verify Health Check Path is set to `/api/health`.

---

## 3. Render Staging Environment Variables Table

Configure the following variables in the Render Dashboard for `chainvault-api`:

| Variable | Staging Setting / Value | Classification | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `staging` | Public Configuration | Enforces staging security guardrails and preflight checks |
| `REQUIRE_PERSISTENT_STORAGE` | `true` | Public Configuration | Fails closed if primary database connection drops |
| `DATABASE_BACKEND` | `firestore` | Public Configuration | Sets Google Cloud Firestore as primary database engine |
| `FIREBASE_PROJECT_ID` | `chainvault-staging` | Public Configuration | GCP Project ID for staging Firestore |
| `FIRESTORE_DATABASE_ID` | `(default)` | Public Configuration | Firestore database instance ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/etc/secrets/gcp-service-account.json` | Secret File Path | Mount path of GCP service account keyfile |
| `JWT_SECRET` | *[Auto-generated 256-bit random key]* | Secret Key | Generated automatically by Render Blueprint |
| `JWT_EXPIRE_MINUTES` | `60` | Public Configuration | Session expiration window (60 minutes) |
| `SUPER_ADMIN_INITIAL_USERNAME` | `superadmin` | Public Configuration | Initial Super Admin identity |
| `SUPER_ADMIN_INITIAL_PASSWORD` | *[Set in Render Dashboard]* | Secret Credential | Strong initial password ($\ge$ 12 chars, non-default) |
| `ADMIN_INITIAL_PASSWORD` | *[Set in Render Dashboard]* | Secret Credential | Strong initial admin password ($\ge$ 12 chars) |
| `INVESTIGATOR_INITIAL_PASSWORD`| *[Set in Render Dashboard]* | Secret Credential | Strong initial investigator password ($\ge$ 12 chars) |
| `BLOCKCHAIN_RPC_URL` | `https://eth-sepolia.g.alchemy.com/v2/...` | Secret RPC URL | Sepolia JSON-RPC provider endpoint |
| `BLOCKCHAIN_CHAIN_ID` | `11155111` | Public Configuration | Ethereum Sepolia Testnet Chain ID |
| `CONTRACT_ADDRESS` | `0x...` *(from sepolia deployment)* | Public Configuration | Deployed `EvidenceRegistryV2` contract address |
| `STORAGE_PATH` | `/var/data/evidence` | Disk Path | Physical evidence storage directory on persistent disk |
| `REPORTS_PATH` | `/var/data/reports` | Disk Path | Forensic PDF inspection reports on persistent disk |
| `PUBLIC_VERIFICATION_URL_BASE` | `https://chainvault-api.onrender.com` | Public URL | Public HTTPS base URL for tamper-evident QR verification |
| `LOCAL_VERIFICATION_URL_BASE` | `http://localhost:8000` | Fallback | Local development fallback link |
| `ALLOW_LOCAL_QR_LINKS` | `false` | Security Policy | Rejects unroutable localhost links in reports |
| `CORS_ORIGINS` | `https://chainvault-frontend.onrender.com` | Security Policy | Strict CORS origin filtering for browser requests |
| `TRUSTED_PROXIES` | `127.0.0.1,::1,10.0.0.0/8` | Security Policy | Render edge reverse proxy CIDRs for rate limiter IP resolution |

---

## 4. Frontend URL Resolution & Verification Links

1. **Automatic Render Domain Auto-Detection**:
   - When hosted on Render (`chainvault-frontend.onrender.com`), [`frontend/js/api.js`](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/api.js) automatically resolves the backend API at `https://chainvault-api.onrender.com/api`.
2. **Explicit Runtime Injection (`frontend/js/config.js`)**:
   - To bind a custom domain or override backend URL, set `window.__CHAINVAULT_API_URL__ = "https://your-custom-api.com/api";` in [`frontend/js/config.js`](file:///d:/parjaayi%20project/CHAINVAULT/frontend/js/config.js).
3. **Query Parameter Flexibility**:
   - Accessing `https://chainvault-frontend.onrender.com?api=https://chainvault-api.onrender.com/api` dynamically sets and caches the target endpoint in browser `localStorage`.
4. **QR Code Links**:
   - Because `PUBLIC_VERIFICATION_URL_BASE=https://chainvault-api.onrender.com` is configured, generated forensic PDF reports embed HTTPS QR verification links:
     `https://chainvault-api.onrender.com/api/verification/verify?evidence_id=EV-XXXX`
   - Fails closed if any localhost link is attempted.

---

## 5. Post-Deployment Verification & Smoke Tests

After deploying to Render, execute these non-destructive smoke tests:

### 5.1 API Health & Firestore Diagnostics
```bash
curl -i https://chainvault-api.onrender.com/api/health
# Expected: HTTP 200 {"status":"ok","service":"ChainVault API"}
```

### 5.2 Sepolia Blockchain & Smart Contract Status
```bash
curl -i https://chainvault-api.onrender.com/api/blockchain/status
# Expected: HTTP 200 {"connected":true,"chain_id":11155111,"contract_deployed":true,"contract_address":"0x..."}
```

### 5.3 Authentication & Portal Navigation
1. Open `https://chainvault-frontend.onrender.com/login.html`.
2. Authenticate with Super Admin credentials $\rightarrow$ Redirects to Platform Owner Console (`superadmin.html`).
3. Verify top status badge displays `🟢 API Online`.
4. Authenticate with Admin credentials $\rightarrow$ Redirects to Evidence Dashboard (`dashboard.html`).

### 5.4 Persistent Disk Verification
1. Upload a sample test evidence file through the dashboard.
2. In the Render Dashboard, trigger **Manual Deploy** or **Restart Service**.
3. Re-check the evidence item:
   - File bytes remain intact on `/var/data/evidence`.
   - Independent verification status reports `VERIFIED`.

---

## 6. Render Plan Limitations & Operational Notes

1. **Persistent Disk Plan Requirement**:
   - Render's **Free Tier does not support Persistent Disks**.
   - Attaching `/var/data` (10GB) requires the **Standard or Starter Plan** ($7 – $25/month).
   - Persistent disks can only be attached to a single web service instance (not multi-instance horizontal autoscaling).
2. **Secret Files**:
   - Google Cloud credentials must be uploaded as a Secret File (`/etc/secrets/gcp-service-account.json`) rather than inlined into environment variable text to prevent key truncation or escape errors.
3. **Outbound IP Addresses**:
   - Render dynamically rotates outbound IP addresses. When configuring Firestore or RPC providers, avoid static IP whitelisting; use service account authentication and API keys.
