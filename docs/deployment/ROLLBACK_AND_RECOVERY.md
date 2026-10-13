# ChainVault — Rollback & Disaster Recovery Procedures

**Governance Policy:** `docs/EXACT_ROLLBACK_POLICY.md`  
**Checkpoint Schedule:** `docs/CHECKPOINT_CREATION_TIMING_POLICY.md`  
**Rollback Incident Log:** `docs/ROLLBACK_LOG.md`  

---

## 1. Rollback Ownership & Trigger Severities

- **SEV-1 (Critical Defect):** Data loss, secret exposure, broken authentication, or severe integrity failure.
  - *Action:* Immediate rollback to the last verified stable Git checkpoint.
  - *Approval:* Automatic by Coding Agent; notify Project Owner immediately.
- **SEV-2 (High Defect):** Broken evidence lifecycle, failed blockchain registration, or failed report layout.
  - *Action:* Revert the smallest safe, scoped commit.
  - *Approval:* Coding Agent with regression verification.
- **SEV-3 (Low / Non-Critical):** Cosmetic defects or documentation warnings. No rollback required; fix forward.

---

## 2. Standard Rollback Procedure

```powershell
# 1. Preserve diagnostic logs and current diff
cd "D:\parjaayi project\CHAINVAULT"
git diff > "rollback_diff_$(Get-Date -Format 'yyyyMMdd_HHmmss').patch"

# 2. Check current status
git status

# 3. Roll back to designated verified checkpoint (e.g. 3dafa08 or af13aa9)
git restore <modified-files>
# Or to restore entire working tree to specific commit:
# git checkout <commit-hash> -- .

# 4. Run targeted regression test suite
cd "backend"
.\venv\Scripts\pytest.exe -v

# 5. Record incident in docs/ROLLBACK_LOG.md
```

---

## 3. Disaster Recovery & Backup Restoration

### 3.1 Proven Recovery Point
- Checkpoint `e54d43e` / `3dafa08` verified in `docs/RECOVERY_LOG.md`:
  - 84 tracked files restored matching Git manifest.
  - Zero credential leaks confirmed.
  - Isolated backend import and startup verified.

### 3.2 Evidence File Store Recovery
1. Physical evidence files are located in `backend/storage/evidence/`.
2. Do not delete or overwrite files in this directory during rollbacks.
3. If files need recovery, restore from designated timestamped cold backup archive.
4. Verify bitstream integrity using independent Python re-hash:
   ```powershell
   python -c "import hashlib; print(hashlib.sha256(open('backend/storage/evidence/<file>', 'rb').read()).hexdigest())"
   ```

### 3.3 Blockchain Ledger Reset & Redeployment
If Hardhat node restarts or crashes:
1. Node memory state resets (block height resets to 0).
2. Redeploy contract via:
   ```powershell
   cd "blockchain"
   npx hardhat run scripts/deploy.js --network localhost
   ```
3. Update `CONTRACT_ADDRESS` in `.env` if deployment address changes from `0x5FbDB2315678afecb367f032d93F642f64180aa3`.
