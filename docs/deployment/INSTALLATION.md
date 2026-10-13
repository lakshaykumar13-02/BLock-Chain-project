# ChainVault — Installation & Environment Setup Guide

**Authoritative Path:** `D:\parjaayi project\CHAINVAULT`  
**System Requirements:** Windows 10/11, Python 3.11+ (Detected: 3.13.14), Node.js 20 LTS+ (Detected: v22.20.0), npm 10+, MongoDB Community Server 7.0+, Git 2.40+.

---

## 1. Clone & Repository Setup

```powershell
# Open PowerShell in your projects directory
cd "D:\parjaayi project"
# If cloning fresh:
# git clone <repository-url> CHAINVAULT
cd "CHAINVAULT"
```

---

## 2. Backend Environment Setup (Python)

```powershell
cd "D:\parjaayi project\CHAINVAULT\backend"

# Create Python virtual environment if not already present
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt
```

*Installed Packages include:* FastAPI, Uvicorn, Motor, PyJWT, bcrypt, python-dotenv, qrcode, Pillow, ReportLab, pytest, httpx.

---

## 3. Blockchain EVM Setup (Hardhat)

```powershell
cd "D:\parjaayi project\CHAINVAULT\blockchain"

# Install Node dependencies
npm install

# Compile Solidity smart contracts
npx hardhat compile
```

*Expected Output:* `Compiled 1 Solidity file successfully (or Nothing to compile)`.

---

## 4. Database Setup (MongoDB)

1. Verify MongoDB Community Server is installed and active on port 27017:
   ```powershell
   Get-Service -Name MongoDB
   # If stopped:
   Start-Service -Name MongoDB
   ```
2. Verify TCP socket connectivity:
   ```powershell
   Test-NetConnection -ComputerName 127.0.0.1 -Port 27017
   # TcpTestSucceeded should be True
   ```

---

## 5. Verification of Installation

```powershell
# Execute full backend automated test suite
cd "D:\parjaayi project\CHAINVAULT\backend"
.\venv\Scripts\pytest.exe -v

# Execute smart contract unit test suite
cd "D:\parjaayi project\CHAINVAULT\blockchain"
npx hardhat test
```

All tests should execute with 100% passing status.
