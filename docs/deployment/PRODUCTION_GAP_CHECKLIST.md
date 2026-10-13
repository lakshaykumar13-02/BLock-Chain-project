# ChainVault — Production Gap Checklist

**Target:** Enterprise / Consortium Production Deployment  
**Status:** `BLOCKED — TARGET NOT DEFINED` (Awaiting Project Owner Target Selection)  

This document delineates all technical, operational, and cryptographic differences between the active **Academic Prototype Demonstration Environment** and an enterprise-grade **Production Forensic Deployment**.

---

## 1. Architectural & Infrastructure Gaps

| Dimension | Current Academic Prototype | Enterprise Production Requirement | Remediation Necessary for Production |
|---|---|---|---|
| **Blockchain Network** | Local Hardhat EVM (Single ephemeral node, Chain ID 31337) | Enterprise Private Consortium (e.g., Hyperledger Besu, Polygon Edge, or Quorum) | Provision multi-node PoA network with consensus nodes |
| **Blockchain Gas & Signers** | Pre-funded local Hardhat accounts with public private keys | Hardware Security Module (HSM) or secure KMS-managed custodian keys | Integrate AWS KMS / Vault / Ledger for transaction signing |
| **Database Persistence** | In-memory route store with local MongoDB service | Multi-node MongoDB Replica Set with TLS and SCRAM authentication | Migrate route storage directly to async Motor collections |
| **Evidence Storage** | Local directory `storage/evidence/` (50 MB limit) | S3-compatible Object Storage (MinIO / AWS S3) with WORM immutability | Implement S3 SDK with write-once-read-many (WORM) bucket policies |
| **Transport Security** | Plain HTTP loopback (`127.0.0.1:8000`) | HTTPS / TLS 1.3 with automated Let's Encrypt / Enterprise CA certificates | Deploy Nginx / Caddy reverse proxy with strict SSL configuration |
| **Digital Signature** | SHA-256 independent file checksum digest | X.509 PKCS#7 / PAdES CA-signed cryptographic digital signature | Integrate PyKCS11 or OpenSSL PKCS#7 certificate signing |
| **User Management** | Pre-configured demo accounts (`DEMO_USERS`) | Enterprise Identity Provider (OAuth2 / OIDC / LDAP / SAML) | Integrate Keycloak / Auth0 / Azure AD identity federation |
| **Audit Log Store** | Python append-only memory store (`AUDIT_LOGS_STORE`) | Centralized SIEM / Immutable append-only log cluster | Forward audit events to Elasticsearch / Splunk / OpenSearch |
| **Network Exposure** | Loopback binding (`localhost` / `127.0.0.1`) | Virtual Private Cloud (VPC) with segmented subnets and firewall | Restrict RPC ports; expose only HTTPS through reverse proxy |
| **QR Code Scope** | Encodes `http://localhost:8000/...` | Encodes public FQDN (e.g., `https://verify.chainvault.gov/...`) | Bind verification URL to public domain name |

---

## 2. Production Pre-Deployment Decision Gates

Before initiating production deployment, the Project Owner must decide and approve:
1. **Target Infrastructure Provider:** On-Premise dedicated servers, AWS, Azure, GCP, or Sovereign Government Cloud.
2. **Blockchain Topology:** Enterprise Ethereum (Besu) vs. Hyperledger Fabric vs. Public Layer-2 (e.g., Polygon, Arbitrum).
3. **Evidence Retention & Compliance:** Jurisdictional digital evidence laws, ISO/IEC 27001, and CJIS compliance mandates.
4. **Certificate Authority (CA):** Approved government or enterprise Root CA for X.509 document signing certificates.
