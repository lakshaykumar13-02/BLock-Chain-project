# ChainVault Phase 4F-B.2 — Live Staging Test Preflight & Identity Verification Audit
**Document ID:** `docs/audit/PHASE_4F_B_PREFLIGHT.md`  
**Phase:** Phase 4F-B.2 — Final Live Test Identity Verification (Audit Only; No Live Execution)  
**Audit Timestamp:** 2026-10-24T19:53:00+05:30  
**Target Firebase Project:** `chainvault-staging`  
**Target Firestore Database:** `(default)` (Cloud Firestore, Standard Edition)  
**Active Application Persistence Engine:** `DATABASE_BACKEND=mongodb` (100% Intact, Unswitched)  
**Opt-In Environment Guard:** `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS` (Unset; 20/20 live tests strictly skipped)  

---

## 1. Executive Summary & Preflight Objectives

Following the resolution of preflight discrepancies in Phase 4F-B.1, this Phase 4F-B.2 audit conducts a **final identity verification and traceability audit** across [`backend/tests/test_firestore_staging_live.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py) and [`backend/tests/test_firestore_staging_guardrails.py`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_guardrails.py) prior to any authorized live execution.

### Key Preflight Confirmations Verified in Phase 4F-B.2:
1. **Actual Firestore Document ID Traceability:** Traced every planned document write to its actual Firestore document ID resolved by `FirestoreCollectionAdapter._get_doc_id()`. Verified that every document ID strictly follows `STG-TEST-<32hex_uuid4>-<entity>` and identically matches the tracker's registered ID.
2. **Zero Collision Risk with Application Records:** Confirmed that every document ID incorporates the full 32-character hexadecimal UUID4 run identifier (122 random bits of entropy, $p < 10^{-36}$). No production or staging records follow the `STG-TEST-` namespace.
3. **100% Pre-Registration & Uniform Ownership Marker:** All 23 planned document creations are registered in `tracker.record_document_creation()` **before** `insert_one()`. Every payload is stamped with `_test_run_marker = STG-RUN-<32hex_uuid4>`.
4. **Atomic Transactional Deletion:** Verified that the live Cloud Firestore client path (`client.firestore_client`) executes atomic transactional deletion using `AsyncClient.transaction()` and `@async_transactional` under Firestore OCC.
5. **Target Configuration Invariance:** Verified that `staging_client` enforces `REQUIRED_PROJECT_ID = "chainvault-staging"`, `REQUIRED_DATABASE_ID = "(default)"`, rejects active emulator hosts, and asserts `DATABASE_BACKEND=mongodb`.
6. **Offline Guardrail Suite:** 21/21 offline guardrail tests passed in 2.97s; all 20 live cloud tests remained skipped. Full regression suite confirmed at 288 passed, 20 skipped, 0 failures. Local MongoDB `chainvault` verified at exactly 6 records.

---

## 2. Line-by-Line Document Count Reconciliation

$$\text{Total Documents} = 2 (\text{cases}) + 8 (\text{evidence}) + 1 (\text{users}) + 7 (\text{audit\_logs}) + 4 (\text{reports}) + 1 (\text{custody\_transactions}) = 23$$

- **Creations:** Exactly **23 document creations** across 6 collections.
- **Deletions:** Exactly **23 document deletions** during fixture teardown.
- **Files:** Exactly **2 temporary files** created in isolated `tempfile.TemporaryDirectory` paths, unlinked during teardown.

---

## 3. Final Live Test Identity Verification & Document ID Traceability Matrix

How `FirestoreCollectionAdapter.insert_one(doc)` resolves document IDs:
```python
doc_id = self._get_doc_id(doc) or doc.get("event_id") or doc.get("transaction_id") or doc.get("report_id")
doc_ref = col_ref.document(str(doc_id))
await doc_ref.create(data)
```
Each collection's primary key (`self.primary_key`) dictates the exact Firestore document key:

| Test ID | Test Function Name | Target Collection | Primary Key Field | Payload ID Field | Actual Cloud Firestore Document Key | Contains Full 32-Char UUID4? | Pre-Reg Confirmed | Overlap with App Records? |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| **2.1** | `test_suite2_case_document_deterministic_id_crud` | `cases` | `case_id` | `case_id` | `STG-TEST-<run_id>-CS-01` | **YES** | [Line 359](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L359) | **ZERO** (`STG-TEST-` prefix) |
| **2.2** | `test_suite2_duplicate_id_atomic_rejection` | `cases` | `case_id` | `case_id` | `STG-TEST-<run_id>-CS-DUP` | **YES** | [Line 381](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L381) | **ZERO** (`STG-TEST-` prefix) |
| **2.3** | `test_suite2_atomic_update_and_increment` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-UPDATE` | **YES** | [Line 399](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L399) | **ZERO** (`STG-TEST-` prefix) |
| **2.4** | `test_suite2_primitive_type_serialization` | `users` | `username` | `username` | `STG-TEST-<run_id>-USR-01` | **YES** | [Line 428](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L428) | **ZERO** (`STG-TEST-` prefix) |
| **3.1** | `test_suite3_canonical_timestamp_rfc3339_string_preservation` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-TIME-01` | **YES** | [Line 458](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L458) | **ZERO** (`STG-TEST-` prefix) |
| **3.2a** | `test_suite3_sequential_merkle_audit_chain_verification` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-SEQ-1` | **YES** | [Line 489](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L489) | **ZERO** (`STG-TEST-` prefix) |
| **3.2b** | `test_suite3_sequential_merkle_audit_chain_verification` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-SEQ-2` | **YES** | [Line 489](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L489) | **ZERO** (`STG-TEST-` prefix) |
| **3.2c** | `test_suite3_sequential_merkle_audit_chain_verification` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-SEQ-3` | **YES** | [Line 489](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L489) | **ZERO** (`STG-TEST-` prefix) |
| **3.3a** | `test_suite3_composite_index_query_execution` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-IDX-3` | **YES** | [Line 518](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L518) | **ZERO** (`STG-TEST-` prefix) |
| **3.3b** | `test_suite3_composite_index_query_execution` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-IDX-1` | **YES** | [Line 518](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L518) | **ZERO** (`STG-TEST-` prefix) |
| **3.3c** | `test_suite3_composite_index_query_execution` | `audit_logs` | `event_id` | `event_id` | `STG-TEST-<run_id>-EVT-IDX-2` | **YES** | [Line 518](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L518) | **ZERO** (`STG-TEST-` prefix) |
| **4.1** | `test_suite4_atomic_lease_lock_acquisition` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-LOCK-01` | **YES** | [Line 547](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L547) | **ZERO** (`STG-TEST-` prefix) |
| **4.2** | `test_suite4_concurrent_lease_collision_rejection` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-COLLIDE-01` | **YES** | [Line 575](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L575) | **ZERO** (`STG-TEST-` prefix) |
| **4.3** | `test_suite4_lease_renewal_verification` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-RENEW-01` | **YES** | [Line 606](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L606) | **ZERO** (`STG-TEST-` prefix) |
| **4.4** | `test_suite4_fencing_version_increment_on_release` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-FENCE-01` | **YES** | [Line 633](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L633) | **ZERO** (`STG-TEST-` prefix) |
| **4.5** | `test_suite4_stale_fencing_version_rejection` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-STALE-01` | **YES** | [Line 665](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L665) | **ZERO** (`STG-TEST-` prefix) |
| **5.1** | `test_suite5_storage_decoupling_evidence_binary_on_disk` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-DECOUPLED-01` | **YES** | [Line 717](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L717) | **ZERO** (`STG-TEST-` prefix) |
| **5.2** | `test_suite5_forensic_report_metadata_and_verification` | `reports` | `report_id` | `report_id` | `STG-TEST-<run_id>-REP-01` | **YES** | [Line 750](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L750) | **ZERO** (`STG-TEST-` prefix) |
| **5.3a** | `test_suite5_composite_index_report_case_chronology` | `reports` | `report_id` | `report_id` | `STG-TEST-<run_id>-REP-CHRONO-1` | **YES** | [Line 773](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L773) | **ZERO** (`STG-TEST-` prefix) |
| **5.3b** | `test_suite5_composite_index_report_case_chronology` | `reports` | `report_id` | `report_id` | `STG-TEST-<run_id>-REP-CHRONO-2` | **YES** | [Line 773](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L773) | **ZERO** (`STG-TEST-` prefix) |
| **5.3c** | `test_suite5_composite_index_report_case_chronology` | `reports` | `report_id` | `report_id` | `STG-TEST-<run_id>-REP-CHRONO-3` | **YES** | [Line 773](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L773) | **ZERO** (`STG-TEST-` prefix) |
| **6.2a** | `test_suite6_full_custody_transfer_lifecycle` | `evidence` | `evidence_id` | `evidence_id` | `STG-TEST-<run_id>-EV-E2E-01` | **YES** | [Line 817](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L817) | **ZERO** (`STG-TEST-` prefix) |
| **6.2b** | `test_suite6_full_custody_transfer_lifecycle` | `custody_transactions` | `transaction_id` | `transaction_id` | `STG-TEST-<run_id>-TX-E2E-01` | **YES** | [Line 835](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L835) | **ZERO** (`STG-TEST-` prefix) |

### 3.1 Traceability Confirmation
- Every document key equals `f"STG-TEST-{tracker.run_id}-{suffix}"`.
- The string `tracker.run_id` is a 32-character hexadecimal UUID4 string.
- Every created document carries `_test_run_marker = f"STG-RUN-{tracker.run_id}"`.
- Document key length: 47 to 56 characters (well below Firestore's 1,500-byte document key limit).
- The offline test [`test_adapter_primary_key_resolutions_match_live_test_entities`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_guardrails.py#L426) programmatically verifies that `FirestoreCollectionAdapter._get_doc_id()` extracts the exact `STG-TEST-` string across all 6 collections.

---

## 4. Run ID Entropy & Collision Resistance

- **UUID4 Hex Entropy:** 122 random bits ($2^{122} \approx 5.3 \times 10^{36}$).
- **Collision Risk Across $10^4$ Staging Runs:** $p < 10^{-29}$ (mathematically zero).
- **Collision Risk with MongoDB/Production:** Zero. Production records use sequential hashes, case numbers (`CASE-2026-XXXX`), or standard UUIDs without `STG-TEST-` prefixes.

---

## 5. TOCTOU & Atomic Transactional Deletion on Cloud Firestore Path

When connected to Google Cloud Firestore via `FirestoreClient`, `cleanup_owned_documents` executes atomic transactions:
```python
doc_ref = fs_client.collection(col_name).document(str(doc_id))
txn = fs_client.transaction()

@async_transactional
async def _txn_delete(transaction):
    snapshot = await doc_ref.get(transaction=transaction)
    if not snapshot.exists:
        return "not_found"
    data = snapshot.to_dict() or {}
    if data.get("_test_run_marker") == self.run_marker:
        transaction.delete(doc_ref)
        return "deleted"
    else:
        return "skipped_unowned"

outcome = await _txn_delete(txn)
```
- Under Cloud Firestore OCC, reading the snapshot and staging `transaction.delete(doc_ref)` are atomic at commit time.
- If the document is modified or deleted concurrently, Cloud Firestore aborts the transaction.

---

## 6. Pre-Flight Safety Guardrails Verification

[`validate_staging_target_safety()`](file:///D:/parjaayi%20project/CHAINVAULT/backend/tests/test_firestore_staging_live.py#L58-L95) enforces the following checks before any client initialization:
1. `project_id == "chainvault-staging"` (Rejects any other GCP project).
2. `database_id == "(default)"` (Rejects any other Firestore database).
3. `emulator_host is None` (Fails if emulator loopback is configured).
4. `active_backend == "mongodb"` (Fails if application engine is switched away from MongoDB).
5. `is_live_testing_opted_in() == True` (Fails if `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS=true` is absent).

---

## 7. Offline Guardrail Test Execution & Validation Results

Executed with `CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS` unset:
```powershell
backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_firestore_staging_guardrails.py backend/tests/test_firestore_staging_live.py
```

### Verified Terminal Output:
```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- D:\parjaayi project\CHAINVAULT\backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\parjaayi project\CHAINVAULT\backend
configfile: pytest.ini
plugins: anyio-4.15.1
collecting ... collected 41 items

backend\tests\test_firestore_staging_guardrails.py::test_opt_in_disabled_by_default PASSED [  2%]
backend\tests\test_firestore_staging_guardrails.py::test_opt_in_enabled_values PASSED [  4%]
backend\tests\test_firestore_staging_guardrails.py::test_opt_in_falsy_values PASSED [  7%]
backend\tests\test_firestore_staging_guardrails.py::test_validate_staging_target_safety_passes_valid_parameters PASSED [  9%]
backend\tests\test_firestore_staging_guardrails.py::test_validate_staging_target_safety_fails_without_opt_in PASSED [ 12%]
backend\tests\test_firestore_staging_guardrails.py::test_validate_staging_target_safety_rejects_wrong_project PASSED [ 14%]
backend\tests\test_firestore_staging_guardrails.py::test_validate_staging_target_safety_rejects_wrong_database PASSED [ 17%]
backend\tests\test_firestore_staging_guardrails.py::test_validate_staging_target_safety_rejects_active_emulator PASSED [ 19%]
backend\tests\test_firestore_staging_guardrails.py::test_validate_staging_target_safety_rejects_non_mongodb_backend PASSED [ 21%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_generates_isolated_deterministic_ids PASSED [ 24%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_prepares_payload_with_ownership_marker PASSED [ 26%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_cleanup_deletes_only_owned_documents PASSED [ 29%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_cleanup_refuses_to_delete_unowned_document PASSED [ 31%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_cleanup_handles_already_deleted_document PASSED [ 34%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_default_run_id_is_full_32char_uuid4_hex PASSED [ 36%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_pre_registration_tracks_and_cleans_up PASSED [ 39%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_pre_registration_handles_aborted_write PASSED [ 41%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_cleanup_via_atomic_transaction_when_available PASSED [ 43%]
backend\tests\test_firestore_staging_guardrails.py::test_tracker_temporary_file_isolation_and_teardown PASSED [ 46%]
backend\tests\test_firestore_staging_guardrails.py::test_sanitize_diagnostic_output_redacts_sensitive_keys PASSED [ 48%]
backend\tests\test_firestore_staging_guardrails.py::test_adapter_primary_key_resolutions_match_live_test_entities PASSED [ 51%]
backend\tests\test_firestore_staging_live.py::test_suite1_cloud_handshake_and_ping SKIPPED [ 53%]
backend\tests\test_firestore_staging_live.py::test_suite1_negative_document_lookup SKIPPED [ 56%]
backend\tests\test_firestore_staging_live.py::test_suite1_empty_collection_streaming SKIPPED [ 58%]
backend\tests\test_firestore_staging_live.py::test_suite2_case_document_deterministic_id_crud SKIPPED [ 60%]
backend\tests\test_firestore_staging_live.py::test_suite2_duplicate_id_atomic_rejection SKIPPED [ 63%]
backend\tests\test_firestore_staging_live.py::test_suite2_atomic_update_and_increment SKIPPED [ 65%]
backend\tests\test_firestore_staging_live.py::test_suite2_primitive_type_serialization SKIPPED [ 68%]
backend\tests\test_firestore_staging_live.py::test_suite3_canonical_timestamp_rfc3339_string_preservation SKIPPED [ 70%]
backend\tests\test_firestore_staging_live.py::test_suite3_sequential_merkle_audit_chain_verification SKIPPED [ 73%]
backend\tests\test_firestore_staging_live.py::test_suite3_composite_index_query_execution SKIPPED [ 75%]
backend\tests\test_firestore_staging_live.py::test_suite4_atomic_lease_lock_acquisition SKIPPED [ 78%]
backend\tests\test_firestore_staging_live.py::test_suite4_concurrent_lease_collision_rejection SKIPPED [ 80%]
backend\tests\test_firestore_staging_live.py::test_suite4_lease_renewal_verification SKIPPED [ 82%]
backend\tests\test_firestore_staging_live.py::test_suite4_fencing_version_increment_on_release SKIPPED [ 85%]
backend\tests\test_firestore_staging_live.py::test_suite4_stale_fencing_version_rejection SKIPPED [ 87%]
backend\tests\test_firestore_staging_live.py::test_suite5_storage_decoupling_evidence_binary_on_disk SKIPPED [ 90%]
backend\tests\test_firestore_staging_live.py::test_suite5_forensic_report_metadata_and_verification SKIPPED [ 92%]
backend\tests\test_firestore_staging_live.py::test_suite5_composite_index_report_case_chronology SKIPPED [ 95%]
backend\tests\test_firestore_staging_live.py::test_suite6_system_diagnostics_integration SKIPPED [ 97%]
backend\tests\test_firestore_staging_live.py::test_suite6_full_custody_transfer_lifecycle SKIPPED [100%]

======================= 21 passed, 20 skipped in 2.97s ========================
```

### Full Backend Regression Suite:
```
=========== 288 passed, 20 skipped, 4 warnings in 274.92s (0:04:34) ===========
```

### Authoritative MongoDB Baseline Verification:
Direct inspection of local MongoDB `localhost:27017`, database `chainvault`:
- `idempotency_records`: 0
- `audit_logs`: 3
- `cases`: 0
- `evidence`: 2
- `blockchain_checkpoints`: 1
- `reports`: 0  
**Total Authoritative Records:** Exactly 6 records, 100% verified intact.

---

## 8. Residual Risk Register

| Risk ID | Risk Description | Probability | Impact | Mitigation / Status |
| :--- | :--- | :---: | :---: | :--- |
| **RSK-01** | Accidental cloud writes during automated test runs | Negligible | Low | Opt-in guard (`CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS=true`) defaults closed. 20/20 live tests skip automatically. |
| **RSK-02** | Test document collisions with existing or future data | Zero | High | 128-bit UUID4 hex run IDs (`STG-TEST-<32hex>-...`) eliminate collision probability ($p < 10^{-36}$). |
| **RSK-03** | Orphaned test records due to network or test failures | Low | Low | Pre-registration ensures documents are queued for cleanup *before* write attempt. Fixture `finally:` block executes unconditionally. |
| **RSK-04** | TOCTOU race condition during cleanup | Very Low | Low | Atomic transactional deletion via `AsyncClient.transaction()` OCC commits. Limitation disclosed; no race-free claim across external actors. |
| **RSK-05** | Authoritative MongoDB data contamination | Zero | Critical | Live test runner connects exclusively to Cloud Firestore via direct ADC; zero network calls or imports touch MongoDB `chainvault`. |

---

## 9. Final Preflight Conclusion & Blockers Evaluation

### Blocker Evaluation:
- **Identity & Primary Key Alignment:** 23/23 documents traced to actual Firestore document IDs. (No blocker)
- **Entropy & Collision Resistance:** Full 32-character hex UUID4 active. (No blocker)
- **Pre-Registration Tracking:** Verified in code and unit tests. (No blocker)
- **Atomic Deletion on Live Client:** Verified via `@async_transactional`. (No blocker)
- **Target Project & Safety Guardrails:** Verified for `chainvault-staging` and `DATABASE_BACKEND=mongodb`. (No blocker)
- **Active Blockers Identified:** **NONE.**

### Recommendation: **GO FOR PHASE 4F-C (LIVE TEST EXECUTION)**
When explicit authorization is granted by the operator, live tests can be executed via PowerShell:

```powershell
# Set explicit opt-in for current session only
$env:CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS="true"

# Execute live staging tests
backend\venv\Scripts\python.exe -m pytest -v backend/tests/test_firestore_staging_live.py

# Unset opt-in immediately after execution
Remove-Item Env:\CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS
```
