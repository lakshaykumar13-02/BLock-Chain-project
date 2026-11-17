# ChainVault Phase 4F-C — Live Staging Test Execution Audit Report
**Document ID:** `docs/audit/PHASE_4F_C_LIVE_TEST_RESULTS.md`  
**Phase:** Phase 4F-C — Authorized Live Staging Execution  
**Execution Timestamp:** 2026-10-24T21:07:13+05:30 to 2026-10-24T21:07:38+05:30  
**Target Firebase Project:** `chainvault-staging`  
**Target Firestore Database:** `(default)` (Cloud Firestore Standard Edition)  
**Active Application Persistence Engine:** `DATABASE_BACKEND=mongodb` (100% Intact, Unswitched)  
**Opt-In Environment Guard:** `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS` (Revoked; strictly unset)  

---

## 1. Executive Summary & Authorization Context

Following explicit operator authorization granted for Phase 4F-C, the live staging integration test suite was executed against the live Cloud Firestore database in Google Cloud project `chainvault-staging` using Windows Application Default Credentials (ADC).

Prior to dispatching cloud calls, all 7 safety conditions of the Final Safety Gate were revalidated and passed. The test suite was invoked under the approved try-finally execution wrapper in PowerShell.

### High-Level Execution Outcome:
- **Test Exit Code:** `1` (Failure)
- **Suite Composition:** 20 collected tests across 6 functional suites.
- **Results:** **1 Passed, 19 Failed, 16 Teardown Errors, 15 Warnings, 0 Skipped.**
- **Cloud Firestore Mutations / Partial Writes:** **ZERO.** No documents were created, modified, or orphaned in Cloud Firestore. Collection probe confirmed `chainvault-staging` has **0 collections**.
- **MongoDB Data Integrity:** **100% PRESERVED.** Local authoritative MongoDB `chainvault` holds **exactly 6 records**.
- **Application Backend:** `DATABASE_BACKEND=mongodb` remained completely untouched.
- **Environment Guard:** `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS` was automatically deleted in the `finally:` block.

---

## 2. Command Execution & Raw Terminal Output

### Invoked PowerShell Command:
```powershell
$ErrorActionPreference = 'Stop'
$env:CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS = 'true'

try {
    backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_firestore_staging_live.py
    $testExitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:\CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS -ErrorAction SilentlyContinue
}

if ($null -eq $testExitCode) {
    throw 'Test execution did not produce an exit code.'
}
Write-Output "Live test exit code: $testExitCode"
```

### Pytest Terminal Summary Output:
```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\parjaayi project\CHAINVAULT\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\parjaayi project\CHAINVAULT\backend
configfile: pytest.ini
plugins: anyio-4.15.1
collecting ... collected 20 items

backend\tests\test_firestore_staging_live.py::test_suite1_cloud_handshake_and_ping PASSED [  5%]
backend\tests\test_firestore_staging_live.py::test_suite1_negative_document_lookup FAILED [ 10%]
backend\tests\test_firestore_staging_live.py::test_suite1_empty_collection_streaming FAILED [ 15%]
backend\tests\test_firestore_staging_live.py::test_suite2_case_document_deterministic_id_crud FAILED [ 20%]
backend\tests\test_firestore_staging_live.py::test_suite2_case_document_deterministic_id_crud ERROR [ 20%]
backend\tests\test_firestore_staging_live.py::test_suite2_duplicate_id_atomic_rejection FAILED [ 25%]
backend\tests\test_firestore_staging_live.py::test_suite2_duplicate_id_atomic_rejection ERROR [ 25%]
backend\tests\test_firestore_staging_live.py::test_suite2_atomic_update_and_increment FAILED [ 30%]
backend\tests\test_firestore_staging_live.py::test_suite2_atomic_update_and_increment ERROR [ 30%]
backend\tests\test_firestore_staging_live.py::test_suite2_primitive_type_serialization FAILED [ 35%]
backend\tests\test_firestore_staging_live.py::test_suite2_primitive_type_serialization ERROR [ 35%]
backend\tests\test_firestore_staging_live.py::test_suite3_canonical_timestamp_rfc3339_string_preservation FAILED [ 40%]
backend\tests\test_firestore_staging_live.py::test_suite3_canonical_timestamp_rfc3339_string_preservation ERROR [ 40%]
backend\tests\test_firestore_staging_live.py::test_suite3_sequential_merkle_audit_chain_verification FAILED [ 45%]
backend\tests\test_firestore_staging_live.py::test_suite3_sequential_merkle_audit_chain_verification ERROR [ 45%]
backend\tests\test_firestore_staging_live.py::test_suite3_composite_index_query_execution FAILED [ 50%]
backend\tests\test_firestore_staging_live.py::test_suite3_composite_index_query_execution ERROR [ 50%]
backend\tests\test_firestore_staging_live.py::test_suite4_atomic_lease_lock_acquisition FAILED [ 55%]
backend\tests\test_firestore_staging_live.py::test_suite4_atomic_lease_lock_acquisition ERROR [ 55%]
backend\tests\test_firestore_staging_live.py::test_suite4_concurrent_lease_collision_rejection FAILED [ 60%]
backend\tests\test_firestore_staging_live.py::test_suite4_concurrent_lease_collision_rejection ERROR [ 60%]
backend\tests\test_firestore_staging_live.py::test_suite4_lease_renewal_verification FAILED [ 65%]
backend\tests\test_firestore_staging_live.py::test_suite4_lease_renewal_verification ERROR [ 65%]
backend\tests\test_firestore_staging_live.py::test_suite4_fencing_version_increment_on_release FAILED [ 70%]
backend\tests\test_firestore_staging_live.py::test_suite4_fencing_version_increment_on_release ERROR [ 70%]
backend\tests\test_firestore_staging_live.py::test_suite4_stale_fencing_version_rejection FAILED [ 75%]
backend\tests\test_firestore_staging_live.py::test_suite4_stale_fencing_version_rejection ERROR [ 75%]
backend\tests\test_firestore_staging_live.py::test_suite5_storage_decoupling_evidence_binary_on_disk FAILED [ 80%]
backend\tests\test_firestore_staging_live.py::test_suite5_storage_decoupling_evidence_binary_on_disk ERROR [ 80%]
backend\tests\test_firestore_staging_live.py::test_suite5_forensic_report_metadata_and_verification FAILED [ 85%]
backend\tests\test_firestore_staging_live.py::test_suite5_forensic_report_metadata_and_verification ERROR [ 85%]
backend\tests\test_firestore_staging_live.py::test_suite5_composite_index_report_case_chronology FAILED [ 90%]
backend\tests\test_firestore_staging_live.py::test_suite5_composite_index_report_case_chronology ERROR [ 90%]
backend\tests\test_firestore_staging_live.py::test_suite6_system_diagnostics_integration FAILED [ 95%]
backend\tests\test_firestore_staging_live.py::test_suite6_full_custody_transfer_lifecycle FAILED [100%]
backend\tests\test_firestore_staging_live.py::test_suite6_full_custody_transfer_lifecycle ERROR [100%]

============ 19 failed, 1 passed, 15 warnings, 16 errors in 16.90s ============
Live test exit code: 1
```

---

## 3. Deep Root-Cause Analysis

### Error Manifestation
Every failing test and fixture teardown failed with the identical exception:
```python
RuntimeError: Event loop is closed
```
Originating from the gRPC async channel transport layer:
```
backend\venv\Lib\site-packages\grpc\aio\_channel.py:185: in __call__
    call = InterceptedUnaryUnaryCall(...)
backend\venv\Lib\site-packages\grpc\aio\_interceptor.py:668: in __init__
    interceptors_task = loop.create_task(...)
C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\Lib\asyncio\base_events.py:466: in create_task
    self._check_closed()
E   RuntimeError: Event loop is closed
```

### Technical Root Cause
1. In [`backend/tests/test_firestore_staging_live.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py), the `staging_client` fixture is defined with module scope:
   ```python
   @pytest.fixture(scope="module")
   def staging_client():
       client = FirestoreClient()
       run_async(client.connect())
       yield client
       run_async(client.close())
   ```
2. The helper function `run_async(coro)` delegates directly to `asyncio.run(coro)`:
   ```python
   def run_async(coro):
       return asyncio.run(coro)
   ```
3. In Python's `asyncio` standard library, `asyncio.run()` creates a brand-new `ProactorEventLoop`, runs the given coroutine to completion, and **immediately closes that loop**.
4. When `client.connect()` ran inside `staging_client`, Google Cloud's `AsyncClient` instantiated its underlying gRPC async channel (`grpc.aio.Channel`), which internally bound itself to the active event loop.
5. As soon as `client.connect()` finished, `asyncio.run()` closed that loop.
6. When individual synchronous test functions subsequently invoked `run_async(_test())`, a *new* event loop was instantiated for the test function. However, the shared `staging_client`'s cached gRPC channel and interceptors still held references to the *closed* event loop from step 4.
7. Calling any gRPC method on that channel caused gRPC to execute `loop.create_task()` on the closed loop, triggering `RuntimeError: Event loop is closed`.
8. The same mechanism caused the fixture teardown `tracker` (`stats = run_async(run_tracker.cleanup_owned_documents(staging_client))`) to fail with `ERROR` status.

---

## 4. Verification of Cleanup, Leftovers & State Integrity

Immediately following execution, independent diagnostic probes were run against Cloud Firestore, local storage, and local MongoDB:

### 4.1 Cloud Firestore Staging Inspection
Direct inspection of `chainvault-staging` database `(default)` via standalone `firestore_v1.AsyncClient`:
- **Top-Level Collections Found:** `[]` (Empty list)
- **Total Test Documents Created:** **0**
- **Total Test Documents Leftover:** **0**
- **Partial Writes:** **None.** All requests aborted locally in `grpc.aio` prior to payload transmission.
- **Unowned / Staging Document Deletions:** **0** (No documents existed or were targeted).

### 4.2 Temporary File System Inspection
- **Temporary Synthetic Evidence / Report Files:** All synthetic files were bound to `tempfile.TemporaryDirectory`. Zero files remain on disk. Real storage directories (`backend/storage/evidence`) were never touched.

### 4.3 Authoritative MongoDB Baseline Recount
Direct recount of local MongoDB `chainvault` (`localhost:27017`):

| Collection | Document Count | Integrity Status |
| :--- | :---: | :---: |
| `idempotency_records` | **0** | Intact |
| `audit_logs` | **3** | Intact |
| `cases` | **0** | Intact |
| `evidence` | **2** | Intact |
| `blockchain_checkpoints` | **1** | Intact |
| `reports` | **0** | Intact |
| **Total Database Records** | **6** | **100% UNTOUCHED** |

### 4.4 Environment & Backend State
- `DATABASE_BACKEND`: `mongodb` (Verified intact)
- `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS`: `None` (Verified successfully removed by PowerShell `finally:` block)
- `FIRESTORE_EMULATOR_HOST`: `None` (Verified unset)

---

## 5. Summary Table of Test Results

| Test # | Suite | Test Identifier | Result | Failure Class / Details |
| :---: | :---: | :--- | :---: | :--- |
| **1.1** | Suite 1 | `test_suite1_cloud_handshake_and_ping` | **PASSED** | Probe evaluated successfully. |
| **1.2** | Suite 1 | `test_suite1_negative_document_lookup` | **FAILED** | `RuntimeError: Event loop is closed` on `batch_get_documents`. |
| **1.3** | Suite 1 | `test_suite1_empty_collection_streaming` | **FAILED** | `RuntimeError: Event loop is closed` on `run_query`. |
| **2.1** | Suite 2 | `test_suite2_case_document_deterministic_id_crud` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **2.2** | Suite 2 | `test_suite2_duplicate_id_atomic_rejection` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **2.3** | Suite 2 | `test_suite2_atomic_update_and_increment` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **2.4** | Suite 2 | `test_suite2_primitive_type_serialization` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **3.1** | Suite 3 | `test_suite3_canonical_timestamp_rfc3339_string_preservation` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **3.2** | Suite 3 | `test_suite3_sequential_merkle_audit_chain_verification` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **3.3** | Suite 3 | `test_suite3_composite_index_query_execution` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **4.1** | Suite 4 | `test_suite4_atomic_lease_lock_acquisition` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **4.2** | Suite 4 | `test_suite4_concurrent_lease_collision_rejection` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **4.3** | Suite 4 | `test_suite4_lease_renewal_verification` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **4.4** | Suite 4 | `test_suite4_fencing_version_increment_on_release` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **4.5** | Suite 4 | `test_suite4_stale_fencing_version_rejection` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **5.1** | Suite 5 | `test_suite5_storage_decoupling_evidence_binary_on_disk` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **5.2** | Suite 5 | `test_suite5_forensic_report_metadata_and_verification` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **5.3** | Suite 5 | `test_suite5_composite_index_report_case_chronology` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |
| **6.1** | Suite 6 | `test_suite6_system_diagnostics_integration` | **FAILED** | `RuntimeError: Event loop is closed` on diagnostic status check. |
| **6.2** | Suite 6 | `test_suite6_full_custody_transfer_lifecycle` | **FAILED + ERROR** | `RuntimeError: Event loop is closed` on `insert_one` & teardown. |

---

## 6. Phase 4F-C Remediation — Test Harness Event Loop Fix

### 6.1 Root Cause & Solution Summary
- **Root Cause:** When `staging_client` called `run_async(client.connect())` using `asyncio.run()`, Python created an event loop, initialized Google Cloud Firestore's `AsyncClient` and underlying `grpc.aio.Channel`, and then destroyed the loop. Subsequent test calls to `run_async()` created distinct event loops, but the shared gRPC channel retained references to the closed event loop, triggering `RuntimeError: Event loop is closed` on `loop.create_task()`.
- **Solution Implemented:**
  1. Implemented `get_staging_event_loop()` and updated `run_async(coro)` in [`backend/tests/test_firestore_staging_live.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py) to manage a persistent, dedicated event loop for the test module.
  2. Updated `staging_client` fixture teardown to close `FirestoreClient` on the same loop, cancel any pending asyncio tasks cleanly, and close the loop upon module completion.
  3. Added Section 6 unit tests in [`backend/tests/test_firestore_staging_guardrails.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_guardrails.py) to verify offline that `get_staging_event_loop()` maintains loop identity across sequential calls and safely recreates the loop if closed.

### 6.2 Offline Test Verification Results
- **Guardrail Unit Suite:**
  ```powershell
  backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_firestore_staging_guardrails.py backend/tests/test_firestore_staging_live.py
  # Result: 23 passed, 20 skipped in 4.66s
  ```
- **Full Backend Regression Suite:**
  ```powershell
  backend\venv\Scripts\python.exe -m pytest -v
  # Result: 291 passed, 20 skipped, 4 warnings in 292.86s (0:04:52)
  ```
  All 291 application tests passed. All 20 live Cloud Firestore tests remained strictly skipped.

### 6.3 State & Integrity Revalidation
- **Cloud Firestore `chainvault-staging` (default):** Read-only probe confirmed `[]` collections (zero documents exist).
- **Local MongoDB `chainvault`:** Recount confirmed exactly 6 records (3 audit_logs, 2 evidence, 1 blockchain_checkpoints).
- **Application Engine:** `DATABASE_BACKEND=mongodb` intact and unswitched.
- **Opt-In Guard:** `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS` is strictly **UNSET**.

### 6.4 Status: Live Tests NOT Yet Rerun
In strict adherence to governance constraints, **live Cloud Firestore tests have NOT yet been rerun**. Awaiting explicit operator authorization to execute the remediated Phase 4F-C live test suite.
