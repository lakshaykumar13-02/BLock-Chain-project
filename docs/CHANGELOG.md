# CHANGELOG & CHECKPOINT REGISTRY

This document records all verified checkpoints, Git commit hashes, and backup locations for ChainVault in accordance with the **Checkpoint Creation Timing Policy** (`docs/CHECKPOINT_CREATION_TIMING_POLICY.md`).

---

## Checkpoint Registry

| Checkpoint Identifier | Date & Time | Git Commit Hash / Backup Location | Trigger / Milestone | Test Results / Verification Status | Owner |
|---|---|---|---|---|---|
| `Checkpoint: Phase 1 — Complete` | 2026-10-11 11:13:49 | `a7fd89c403c235e6cb1d4e8e286b7e7b16103d7c` | Phase 1 Completion (Baseline Architecture) | All baseline criteria passed; Contract compile OK; Backend import OK | Coding Agent |
| `Checkpoint: Phase 12 — Testing Audited` | 2026-10-11 11:35:00 | *(Working Tree Commit)* | Phase 12 Testing & Validation Execution | 7 tests passed, 6 blocked/xfailed, BUG-01 resolved; Phase status INCOMPLETE / BLOCKED | Coding Agent |

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
