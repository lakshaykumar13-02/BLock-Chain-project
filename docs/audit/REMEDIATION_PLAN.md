# ChainVault — Remediation Plan & Defect Resolution (Phase F)

**Audit Date:** 2026-10-13  
**Audit Author:** Antigravity Master Project Audit Agent  
**Authoritative Workspace:** `D:\parjaayi project\CHAINVAULT`  
**Current Git Branch:** `master`  

---

## 1. Remediation Priority Framework

- **P0 — Critical:** Data loss, unauthorized evidence access, authentication bypass, secret exposure, or severe integrity failure.
- **P1 — High:** Core evidence workflow broken, incorrect hash verification, invalid custody handling, incorrect authorization, or failed deployment startup.
- **P2 — Medium:** Important functionality incomplete, incorrect report layout, incorrect dashboard data, broken QR behavior, or unreliable persistence.
- **P3 — Low:** Documentation defects, cosmetic issues, minor deprecation warnings, and noncritical usability improvements.

---

## 2. Defect Inventory & Action Plan

### DEF-01: Standalone Hardhat EVM Node Daemon Not Running on Port 8545
- **Finding ID:** `DEF-01`
- **Phase & Affected Feature:** Phase 6 / 13 (Blockchain Integration & Node Connectivity Probe)
- **Reproduction Steps:** Run `pytest tests/integration/test_fastapi_blockchain.py::test_blockchain_rpc_reachability_detection` without Hardhat node running.
- **Expected vs Actual Behavior:** Test expected `check_blockchain_health() is True`, but returned `False` because port 8545 had no active listener.
- **Evidence:** `netstat -ano | findstr 8545` returned no listening process.
- **Severity & Rationale:** **P1 (High)** — Without an active Hardhat daemon, on-chain live transactions fall back to in-process simulation.
- **Planned Fix:**
  1. Start the standalone Hardhat node as a background daemon on port 8545: `npx hardhat node`.
  2. Deploy `EvidenceRegistry.sol` to the local standalone network if needed: `npx hardhat run scripts/deploy.js --network localhost`.
  3. Verify port 8545 responds with HTTP 200 to `net_version` RPC call.
- **Files Expected to Change:** None in codebase; operational service launch.
- **Regression Tests:** `pytest tests/integration/test_fastapi_blockchain.py`.
- **Rollback Strategy:** Terminate Hardhat daemon process.
- **Final Verification Result:** Pending execution in Phase F remediation.

---

### DEF-02: Pytest Windows Teardown `PermissionError [WinError 5]` on `%TEMP%`
- **Finding ID:** `DEF-02`
- **Phase & Affected Feature:** Phase 12 (Testing & Environment Execution)
- **Reproduction Steps:** Run `.\venv\Scripts\pytest.exe -v` directly from PowerShell without `--basetemp` flag.
- **Expected vs Actual Behavior:** Pytest executes 100% of tests, but at session exit crashes in `cleanup_dead_symlinks` trying to delete `pytest-current` in Windows `AppData\Local\Temp`.
- **Evidence:** `PermissionError: [WinError 5] Access is denied: 'C:\Users\Asus\AppData\Local\Temp\pytest-of-Asus\pytest-current'`.
- **Severity & Rationale:** **P2 (Medium)** — Does not invalidate test logic (all tests passed), but disrupts clean CI/local developer execution.
- **Planned Fix:** Update `backend/pytest.ini` to configure `addopts = --basetemp=./.pytest_temp` and ignore legacy path cleanups.
- **Files Expected to Change:** `backend/pytest.ini`
- **Regression Tests:** Run `pytest` with default arguments and verify exit code 0 without traceback.
- **Rollback Strategy:** Revert `backend/pytest.ini`.
- **Final Verification Result:** Pending execution in Phase F remediation.

---

### DEF-03: Starlette Deprecation Warning for `HTTP_413_REQUEST_ENTITY_TOO_LARGE`
- **Finding ID:** `DEF-03`
- **Phase & Affected Feature:** Phase 4 / 11 (Evidence Upload & Security Hardening)
- **Reproduction Steps:** Run `tests/test_security_regression.py::test_input_oversized_upload_rejected`.
- **Expected vs Actual Behavior:** Test passes with HTTP 413, but emits deprecation warning: `'HTTP_413_REQUEST_ENTITY_TOO_LARGE' is deprecated. Use 'HTTP_413_CONTENT_TOO_LARGE' instead`.
- **Evidence:** StarletteDeprecationWarning logged during pytest session.
- **Severity & Rationale:** **P3 (Low)** — Non-breaking warning; future compatibility improvement.
- **Planned Fix:** Update `backend/app/routes/evidence.py` to use `status.HTTP_413_CONTENT_TOO_LARGE`.
- **Files Expected to Change:** `backend/app/routes/evidence.py`
- **Regression Tests:** `tests/test_security_regression.py::test_input_oversized_upload_rejected`.
- **Rollback Strategy:** Revert constant in `evidence.py`.
- **Final Verification Result:** Pending execution in Phase F remediation.

---

### DEF-04: Uncommitted Working Tree Enhancements (Frontend & PDF Layout)
- **Finding ID:** `DEF-04`
- **Phase & Affected Feature:** Phase 10 / 13 (Forensic Reports & Demonstration UI)
- **Reproduction Steps:** Run `git status` in workspace root.
- **Expected vs Actual Behavior:** Repository working tree contains modified and untracked files representing complete interactive UI views and NumberedCanvas PDF generation.
- **Evidence:** 7 modified files and 1 untracked file (`test_pdf_report_layout.py`) in `git status`.
- **Severity & Rationale:** **P1 (High)** — High-value feature work must be verified, preserved, and committed under release checkpoints rather than left uncommitted.
- **Planned Fix:** Validate all layout tests (`test_pdf_report_layout.py`), execute browser verification, and include reviewed files in release checkpoint commit.
- **Files Expected to Change:** Working tree staging.
- **Regression Tests:** `test_pdf_report_layout.py` (7 tests) and full backend suite.
- **Rollback Strategy:** `git checkout` or `git restore` if any defect discovered.
- **Final Verification Result:** Pending execution in Phase F remediation.

---

### DEF-05: Path Reference Inconsistency (`C:\ChainVault` vs `D:\parjaayi project\CHAINVAULT`)
- **Finding ID:** `DEF-05`
- **Phase & Affected Feature:** Phase 1 / Documentation Reference
- **Reproduction Steps:** Search documentation for `C:\ChainVault`.
- **Expected vs Actual Behavior:** Documentation should clearly identify `D:\parjaayi project\CHAINVAULT` as the authoritative repository.
- **Evidence:** References in `docs/CHECKPOINT_CREATION_TIMING_POLICY.md` and `docs/CONFIGURATION_REFERENCE.md`.
- **Severity & Rationale:** **P3 (Low)** — Documentation clarification.
- **Planned Fix:** Document workspace relationship explicitly in audit reports and runbooks.
- **Files Expected to Change:** Audit documentation.
- **Regression Tests:** Cross-reference validation.
- **Rollback Strategy:** Revert text.
- **Final Verification Result:** Verified in `PROJECT_INVENTORY.md` and `DEMO_RUNBOOK.md`.

---

## 3. Remediation Sequence & Dependency Order

1. **Step 1 (DEF-03):** Update `evidence.py` to resolve Starlette 413 deprecation warning.
2. **Step 2 (DEF-02):** Update `backend/pytest.ini` to add local basetemp directory and prevent Windows permission errors.
3. **Step 3 (DEF-01):** Launch local Hardhat node daemon on port 8545 and deploy `EvidenceRegistry.sol`.
4. **Step 4:** Execute targeted Pytest test suites to verify DEF-01, DEF-02, and DEF-03 resolution.
5. **Step 5 (DEF-04):** Verify `test_pdf_report_layout.py` passes and working tree is stable.
