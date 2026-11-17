# ChainVault Production Deployment Plan & Operations Manual

**Status:** Ready for Pre-Deployment Staging  
**Application:** ChainVault Forensic Evidence Management System  
**Version:** 1.0.0 (Production-Hardened)  
**Database Engines:** Google Cloud Firestore (Primary Active) | MongoDB (Rollback Source)  
**Blockchain Engine:** Solidity EvidenceRegistryV2 (EVM / Sepolia / Mainnet / L2 compatible)

---

## 1. System Topology & Architecture

```
[ Browser Clients (Admin / Investigator) ]
                   │
                   ▼ (HTTPS / TLS 1.3)
      [ Reverse Proxy / Load Balancer ]
        (Nginx / Cloudflare / AWS ALB)
                   │
                   ▼ (HTTP / Internal Port 8000)
    [ FastAPI Backend Service (Uvicorn) ]
         │                   │                   │
         ▼                   ▼                   ▼
[ Google Cloud Firestore ]  [ Persistent Volume ]  [ EVM Blockchain ]
(chainvault-prod default)   (/var/data/evidence)   (Infura/Alchemy RPC)
```

---

## 2. Secrets & Credentials Management

### 2.1 Least-Privilege Rules
- **No secrets in Git:** Tracked files (.env.example, hardhat.config.js, etc.) contain strictly sample placeholders.
- **Environment Injection:** Inject secrets via cloud orchestration (Google Cloud Secret Manager, AWS Secrets Manager, or Render Environment Variables).
- **Service Account Permissions:**
  - Google Cloud Service Account must have only `roles/datastore.user`.
  - Do NOT grant `roles/owner` or `roles/editor`.

### 2.2 Production Environment Variables Specification

| Variable | Requirement | Production Value Example |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Must be `production` | `production` |
| `REQUIRE_PERSISTENT_STORAGE` | Must be `true` | `true` |
| `DATABASE_BACKEND` | Active persistence engine | `firestore` |
| `FIREBASE_PROJECT_ID` | Production GCP project | `chainvault-production` |
| `FIRESTORE_DATABASE_ID` | Firestore database instance | `(default)` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service account JSON or GCP ADC | `/etc/secrets/gcp-sa.json` |
| `JWT_SECRET` | 256-bit cryptographically secure string (min 32 chars) | Generated via `openssl rand -hex 32` |
| `JWT_EXPIRE_MINUTES` | Session token lifespan | `60` |
| `ADMIN_INITIAL_PASSWORD` | Strong initial admin credential (min 12 chars) | Generated high-entropy password |
| `INVESTIGATOR_INITIAL_PASSWORD` | Strong initial investigator credential (min 12 chars) | Generated high-entropy password |
| `BLOCKCHAIN_RPC_URL` | EVM JSON-RPC provider (dedicated key) | `https://sepolia.infura.io/v3/PROJECT_KEY` |
| `BLOCKCHAIN_CHAIN_ID` | Network ID (Sepolia: 11155111, Mainnet: 1, Polygon: 137) | `11155111` |
| `CONTRACT_ADDRESS` | Deployed `EvidenceRegistryV2` address | `0x...` |
| `STORAGE_PATH` | Mount directory for evidence files | `/var/data/evidence` |
| `REPORTS_PATH` | Mount directory for forensic PDF reports | `/var/data/reports` |
| `PUBLIC_VERIFICATION_URL_BASE` | Public HTTPS verification portal | `https://verify.chainvault.example.com` |
| `ALLOW_LOCAL_QR_LINKS` | Must be `false` in production | `false` |
| `CORS_ORIGINS` | Explicit domain origins (no wildcards) | `https://chainvault.example.com` |
| `TRUSTED_PROXIES` | IPs of reverse proxy / load balancer | `10.0.0.1,10.0.0.2` |

---

## 3. Reverse Proxy & HTTPS Configuration (Nginx / Load Balancer)

When deploying behind an Nginx reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name api.chainvault.example.com;

    ssl_certificate /etc/letsencrypt/live/api.chainvault.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.chainvault.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

The application's `LoginRateLimiter` verifies that the connecting peer IP matches `TRUSTED_PROXIES` before accepting `X-Forwarded-For`, preventing client IP spoofing attacks.

---

## 4. Firestore Security Rules & IAM Verification

### 4.1 Client Rules ([firestore.rules](file:///D:/parjaayi%20project/CHAINVAULT/firestore.rules))
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```
All client-side direct database reads and writes are rejected. All queries are channeled through the FastAPI backend.

### 4.2 IAM Role Assignment
Deploy the backend using Google Cloud ADC or a dedicated Service Account:
```bash
gcloud projects add-iam-policy-binding chainvault-production \
  --member="serviceAccount:chainvault-backend@chainvault-production.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

---

## 5. Persistent Evidence Storage

Evidence files and forensic PDF reports must be mounted to a persistent cloud volume (e.g. AWS EBS, GCP Persistent Disk, or Render Disk):
- Evidence storage path: `/var/data/evidence`
- Reports storage path: `/var/data/reports`
- Directory permissions: Read/write for the backend application UID.
- Ingestion verification: Every file upload is hashed with SHA-256 upon reception and verified during download and blockchain anchoring.
- Path Traversal Defense: System checks path normalization and forbids null-byte (`\x00`) injections and directory escapes (`..`).

---

## 6. Backup and Disaster Recovery

### 6.1 Firestore Automated Exports
Schedule automated daily backups of Cloud Firestore to Google Cloud Storage (GCS):
```bash
# 1. Create a dedicated backup bucket
gsutil mb -l us-central1 gs://chainvault-prod-backups

# 2. Execute on-demand or scheduled backup
gcloud firestore export gs://chainvault-prod-backups/$(date +%Y%m%d_%H%M%S)

# 3. Restore Firestore from backup
gcloud firestore import gs://chainvault-prod-backups/20261024_120000/
```

### 6.2 MongoDB Disaster Recovery / Instant Rollback
A complete cold backup of all collections is maintained in `backend/backups/mongodb_backup_pre_migration_20261024/`.
To switch back to MongoDB in an emergency:
1. Set `DATABASE_BACKEND=mongodb` in the environment.
2. Provide `MONGO_URI` pointing to the MongoDB cluster.
3. Restart the FastAPI service.

---

## 7. Blockchain Network Selection & Deployment

### 7.1 Network Comparison

| Network | Type | Finality | Est. Gas Fee | Best Used For |
| :--- | :--- | :--- | :--- | :--- |
| **Ethereum Sepolia** | Public Testnet | ~12s | Free (Faucet ETH) | Staging & Validation |
| **Polygon PoS** | Public L2 / Sidechain | ~2s | < $0.01 | High-throughput Production |
| **Arbitrum One** | Public Rollup (L2) | < 1s | ~ $0.05 | High-security Production |
| **Hyperledger Besu** | Enterprise EVM | Instant | $0.00 (Gasless) | Private / Government Consortium |

### 7.2 Deploying to Production (Sepolia Example)
1. Verify deployer wallet is funded with testnet/production gas funds.
2. Run deployment dry-run (no transactions broadcast):
   ```bash
   cd blockchain
   npx hardhat run scripts/deploy_v2_sepolia.js
   ```
3. When authorized, broadcast live deployment:
   ```bash
   DEPLOY_BROADCAST=true SEPOLIA_RPC_URL="https://sepolia.infura.io/v3/..." SEPOLIA_PRIVATE_KEY="<KEY>" npx hardhat run scripts/deploy_v2_sepolia.js --network sepolia
   ```
4. Record the deployed contract address and set `CONTRACT_ADDRESS` in production configuration.

---

## 8. Monitoring & Health Checks

- **Health Check Endpoint:** `GET /api/health` returns `{"status": "ok", "service": "ChainVault API"}` (HTTP 200).
- **Blockchain Connectivity Probe:** Monitored via `GET /api/blockchain/status`.
- **Audit Tamper Detection:** Query `GET /api/audit/verify` to detect any break in the cryptographic hash chain.
- **Brute Force Alerting:** Monitor `HTTP 429` error rates from `/api/auth/login`.
