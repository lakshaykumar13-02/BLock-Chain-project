# CHANGELOG & CHECKPOINT REGISTRY

This document records all verified checkpoints, Git commit hashes, and backup locations for ChainVault in accordance with the **Checkpoint Creation Timing Policy** (`docs/CHECKPOINT_CREATION_TIMING_POLICY.md`).

---

## Checkpoint Registry

| Checkpoint Identifier | Date & Time | Git Commit Hash / Backup Location | Trigger / Milestone | Test Results / Verification Status | Owner |
|---|---|---|---|---|---|
| `Checkpoint: Phase 1 — Complete` | 2026-10-11 11:13:49 | `a7fd89c403c235e6cb1d4e8e286b7e7b16103d7c` | Phase 1 Completion (Baseline Architecture) | All baseline criteria passed; Contract compile OK; Backend import OK | Coding Agent |
| `Checkpoint: Phase 12 — Testing Audited` | 2026-10-11 11:35:00 | `9ccca4d` | Phase 12 Unit & Security Test Audit | 7 tests passed, 6 blocked/xfailed, BUG-01 resolved; Phase status INCOMPLETE / BLOCKED | Coding Agent |
| `Checkpoint: Phase 12 — Integration Audited` | 2026-10-11 11:46:00 | `7dbdeb1` | Phase 12 Integration & E2E Validation | 24 tests passed, 21 blocked/xfailed; 11-step E2E lifecycle audited; Phase status INCOMPLETE / BLOCKED | Coding Agent |
| `Checkpoint: Phase 12 — Regression Verified` | 2026-10-11 11:52:00 | *(Working Tree Commit)* | Phase 12 Regression Testing & Bug Verification | 47 automated tests (24 passed, 23 blocked, 0 regressions, 0 failed); Phase status INCOMPLETE / BLOCKED | Coding Agent |

---

## Detailed Checkpoint History

### Checkpoint: Phase 1 — Complete
- **Timestamp:** 2026-10-11 11:13:49 IST
- **Git Commit:** `a7fd89c403c235e6cb1d4e8e286b7e7b16103d7c`
- **Scope / Changes:**
  - Project foundation and architecture scaffolding established.
  - Smart contract `EvidenceRegistry.sol` compiled with Hardhat.
  - FastAPI backend structure configured with `/api/health` and database layer.
  - Frontend scaffolding with Vanilla HTML5/CSS3/JS for Login and Dashboard.
  - Governance policies established: `EXACT_ROLLBACK_POLICY.md`, `ROLLBACK_LOG.md`, and `CHECKPOINT_CREATION_TIMING_POLICY.md`.
- **Verification Performed:**
  - Smart contracts compilation: Passed (`npx hardhat compile`).
  - Backend modules import: Passed (`Backend import OK`).
  - Sensitive files check: Verified `.gitignore` prevents `.env`, `node_modules`, `venv`, live evidence, and reports from being tracked.
- **Status:** Verified Stable (Phase 1 Complete)
- **Recorded By:** Coding Agent

---

### Checkpoint: Phase 12 — Testing Audited
- **Timestamp:** 2026-10-11 11:35:00 IST
- **Git Commit:** `9ccca4d`
- **Scope / Changes:**
  - Phase 12 test suite created: `backend/tests/` (`test_health.py`, `test_cors.py`, `test_security_baseline.py`, `test_feature_coverage.py`), `blockchain/test/EvidenceRegistry.test.js`.
  - Discovered and resolved BUG-01: Added authorized frontend port 5500 to CORS `origins` in `backend/app/main.py`.
  - Executed automated backend test suite (`pytest -v`) and Hardhat test suite (`npx hardhat test`).
  - Documented complete test deliverables: `docs/testing/TEST_REPORT.md`, `docs/testing/TEST_CASES.md`, `docs/testing/BUG_LOG.md`.
- **Verification Performed:**
  - Backend tests: 6 passed, 6 xfailed/blocked, 0 failed.
  - Blockchain tests: 1 passed, 0 failed.
  - Probed MongoDB: Port 27017 inactive (BUG-03).
  - Identified Phase 2–11 feature implementation gaps (BUG-02).
- **Status:** **INCOMPLETE / BLOCKED** (Phase 12 cannot be marked Complete until underlying features are implemented).
- **Recorded By:** Coding Agent

---

### Checkpoint: Phase 12 — Integration Audited
- **Timestamp:** 2026-10-11 11:46:00 IST
- **Git Commit:** `7dbdeb1`
- **Scope / Changes:**
  - Component integration test suites created under `backend/tests/integration/`:
    - `test_fastapi_mongodb.py`: Database isolation to `chainvault_test` and offline service resilience.
    - `test_fastapi_blockchain.py`: Strict local RPC routing and offline node resilience.
    - `test_frontend_fastapi.py`: Base URL consistency and zero client-side private key/secret leaks.
    - `test_evidence_lifecycle.py`: 11-step end-to-end synthetic evidence lifecycle audit.
  - Created `docs/testing/INTEGRATION_TEST_REPORT.md`.
  - Updated `docs/testing/COVERAGE_MATRIX.md`, `docs/testing/TEST_REPORT.md`, `docs/testing/BUG_LOG.md`.
- **Verification Performed:**
  - Automated tests executed: 45 tests (24 passed, 21 blocked/xfailed, 0 failed).
  - Pre-test safety gate: Target DB `chainvault_test` verified, local RPC verified, zero client secrets verified.
- **Status:** **INCOMPLETE / BLOCKED**
- **Recorded By:** Coding Agent

---

### Checkpoint: Phase 12 — Regression Verified
- **Timestamp:** 2026-10-11 11:52:00 IST
- **Scope / Changes:**
  - Full regression suite executed across 47 automated test items (42 Backend + 5 Blockchain).
  - Added `backend/tests/test_rbac_regression.py` auditing the four user roles (ADMIN, INVESTIGATOR, ANALYST, VIEWER).
  - Independently re-tested BUG-01 (CORS port 5500) -> Verified Fixed.
  - Created `docs/testing/REGRESSION_TEST_REPORT.md`.
- **Verification Performed:**
  - Baseline vs final test comparison: 0 regressions found; all 24 passing tests remained stable.
  - Blocked tests documented: 23 blocked/xfailed due to missing Phases 2–11 implementation.
- **Status:** **INCOMPLETE / BLOCKED**
- **Recorded By:** Coding Agent
