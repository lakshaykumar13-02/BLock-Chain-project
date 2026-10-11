# ChainVault
Blockchain-Based Digital Evidence Integrity & Chain-of-Custody Platform.

## Problem Statement
Maintaining the integrity of digital evidence is crucial in forensics. Standard storage methods can be tampered with.

## Core Concept
ChainVault securely stores evidence metadata and cryptographic hashes on a blockchain while keeping the large evidence files in a secure local or distributed storage system. This ensures a tamper-proof chain of custody.

## Architecture Overview
- **Frontend**: HTML5, CSS3, Vanilla JS
- **Backend**: Python, FastAPI, MongoDB
- **Blockchain**: Solidity, Hardhat, local Ethereum network

---

## Authoritative Tool Matrix & Installation Timeline

ChainVault follows a strict phase-by-phase dependency model. Tools are only required when a phase cannot reasonably be implemented without them.

### Final Installation Timeline

**Before Phase 1 (Project Foundation)**
- Python 3.11+
- PowerShell
- Browser
- Git (Development-required)
- *Recommended: VS Code*

**Before Phase 2 (MongoDB + FastAPI Backend)**
- MongoDB Community Server
- mongosh

**Before Phase 5 (Blockchain Foundation)**
- Node.js 20 LTS+
- npm
- Hardhat dependencies & Solidity tooling

**Before Phase 6 (Blockchain Integration)**
- ethers.js
- MetaMask (Required ONLY if wallet-based signing is used)

**Before Phase 9 (QR Verification)**
- qrcode (Python package)

**Before Phase 10 (Forensic Reports)**
- ReportLab (Python package)

**Before Phase 12 (Testing)**
- pytest
- Hardhat test environment

### Excluded Technologies
This project strictly avoids unnecessary dependencies. It does **NOT** require:
- React, Angular, Vue, Vite
- SQLite, MySQL, PostgreSQL, Redis, Firebase, MongoDB Atlas
- Docker, Kubernetes, WSL, Linux VM

### Final Requirement Check (Phase 1)
For Phase 1 development, verify your core tools in PowerShell:
```powershell
python --version
git --version
```
(Node.js and MongoDB will be verified in their respective phases.)

---

## Exact Local Run Commands

The normal development setup uses three terminals side-by-side. Always start from the fixed project root: `C:\ChainVault`

### Terminal 1 — Backend
```powershell
cd C:\ChainVault\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
# (Use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` if blocked, then activate again)
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item C:\ChainVault\.env.example C:\ChainVault\.env
uvicorn app.main:app --reload
```
* Backend runs at: `http://127.0.0.1:8000`
* FastAPI docs: `http://127.0.0.1:8000/docs`
* Health Check: `http://127.0.0.1:8000/api/health`

### Terminal 2 — Frontend
```powershell
cd C:\ChainVault
cd frontend
python -m http.server 5500
```
* Frontend accessible at: `http://127.0.0.1:5500`

### Terminal 3 — Blockchain (Required from Phase 5)
```powershell
cd C:\ChainVault
cd blockchain
npm install
npx hardhat compile
npx hardhat node
```
* Hardhat RPC runs at: `http://127.0.0.1:8545`

### MongoDB (Required from Phase 2)
MongoDB is a separate local service. The default development connection is:
`mongodb://localhost:27017`

---

## Phase 1 Functionality
- Basic project structure established in `C:\ChainVault`.
- FastAPI initialized with `/api/health`.
- MongoDB connection layer configured (stubbed for Phase 1).
- Basic HTML/CSS/JS scaffolding for Login and Dashboard layout.
- Skeleton Smart Contract (`EvidenceRegistry.sol`) successfully compiled.
