# ChainVault — Defect & Bug Log

This document records all defects, security issues, configuration flaws, and implementation gaps discovered during Phase 12 Testing & Validation, along with their resolution and regression verification.

---

## Defects Registry

| Bug ID | Severity | Component | Summary | Status | Discovered By | Verified In |
|---|---|---|---|---|---|---|
| BUG-01 | Medium (SEV-3) | Backend CORS (`app/main.py`) | Authorized frontend port (5500) missing from CORS `origins` | **Resolved** | Automated Test | `tests/test_cors.py` |
| BUG-02 | High (SEV-2) | System Architecture | Phases 2–11 feature implementations missing (routes and services are stubs) | **Documented / Blocking** | Audit & Coverage Tests | `tests/test_feature_coverage.py` |
| BUG-03 | High (SEV-2) | Infrastructure / DB | Local MongoDB service on `localhost:27017` is not active | **Documented / Blocking** | Connection Probe | `Test-NetConnection` |

---

## Detailed Bug Records

### Bug ID: BUG-01 — Missing Frontend Port 5500 in CORS Configuration
- **Severity:** Medium (SEV-3)
- **Component:** `backend/app/main.py`
- **Summary:** The default local frontend runs at `http://127.0.0.1:5500`, but FastAPI CORS configuration only permitted ports 8080 and 3000. Browser requests from the dashboard or login page to `/api/*` were rejected by the browser due to missing `Access-Control-Allow-Origin` headers.
- **Reproduction Steps:**
  1. Send an `OPTIONS` preflight request to `/api/health` with `Origin: http://127.0.0.1:5500`.
  2. Inspect response headers for `Access-Control-Allow-Origin`.
  3. Fails with `AssertionError: assert None == 'http://127.0.0.1:5500'`.
- **Root Cause:** Hardcoded `origins` list omitted port 5500.
- **Fix Applied:** Added `"http://localhost:5500"` and `"http://127.0.0.1:5500"` to `origins` in `backend/app/main.py`.
- **Regression Test:** `backend/tests/test_cors.py::test_cors_frontend_port_allowed` -> **Passed** (100%).
- **Current Status:** **Resolved & Verified**.

---

### Bug ID: BUG-02 — Missing Endpoints and Core Services (Phases 2 through 11 Stubs)
- **Severity:** High (SEV-2 Blockage)
- **Component:** `backend/app/routes/*`, `backend/app/services/*`, `backend/app/security/*`, `blockchain/contracts/EvidenceRegistry.sol`
- **Summary:** The project resumed Phase 12 validation while still containing only the Phase 1 architectural scaffolding. Business logic endpoints (`/api/auth/login`, `/api/cases`, `/api/evidence/upload`, `/api/custody/transfer`, `/api/verification/verify`, `/api/reports/generate`) and smart contract functions (`registerEvidence`, `transferCustody`, `verifyEvidence`) exist only as placeholders/stubs.
- **Reproduction Steps:**
  1. Execute `pytest -v tests/test_feature_coverage.py`.
  2. Endpoints return HTTP 404 (routes unmounted).
  3. Smart contract exhibits only `admin` state variable; registration functions are unimplemented.
- **Root Cause:** Phases 2–11 development was not executed prior to initiating Phase 12 testing.
- **Fix Required:** Phases 2–11 must be implemented phase-by-phase in accordance with the Master Specification before Phase 12 acceptance criteria can be fully satisfied.
- **Current Status:** **Documented Blocker (Phase 12 Incomplete)**.

---

### Bug ID: BUG-03 — MongoDB Local Service Inactive
- **Severity:** High (SEV-2 Blockage)
- **Component:** Infrastructure / Local Development Database
- **Summary:** TCP socket connection to `localhost:27017` failed. MongoDB Community Server is either not installed or the `mongod` service is currently stopped.
- **Reproduction Steps:**
  1. Execute `Test-NetConnection -ComputerName localhost -Port 27017`.
  2. Returns `TcpTestSucceeded : False`.
- **Root Cause:** MongoDB service is offline in the local environment.
- **Fix Required:** Start the local MongoDB service (`net start MongoDB` or launch `mongod`) prior to running database-dependent test suites.
- **Current Status:** **Documented Blocker**.
