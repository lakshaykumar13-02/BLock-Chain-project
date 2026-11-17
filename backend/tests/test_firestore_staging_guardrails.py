"""
Unit Tests for Firestore Staging Guardrails and Safety Controls
===============================================================
Validates all safety mechanisms of test_firestore_staging_live.py in an offline,
isolated test harness:
1. Opt-in environment variable checking and skip logic.
2. Pre-flight guardrails: project ID, database ID, emulator host, and backend checks.
3. Ownership tracking, deterministic ID generation, and marker injection.
4. Selective cleanup: deleting only owned documents with verified markers.
5. Unowned document safety: rejecting deletion if marker is missing or mismatched.
6. Temporary file isolation and teardown without touching production directories.
7. Diagnostic output sanitization and credential redaction.

NOTE: These tests are purely local and mock all database calls. Zero cloud access.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tests.test_firestore_staging_live import (
    REQUIRED_PROJECT_ID,
    REQUIRED_DATABASE_ID,
    OPT_IN_ENV_VAR,
    StagingSafetyViolation,
    is_live_testing_opted_in,
    validate_staging_target_safety,
    sanitize_diagnostic_output,
    StagingTestRunTracker,
    get_staging_event_loop,
    run_async
)


# =============================================================================
# 1. OPT-IN ENVIRONMENT VARIABLE TESTS
# =============================================================================

def test_opt_in_disabled_by_default(monkeypatch):
    """Verify live testing is disabled when the opt-in variable is unset."""
    monkeypatch.delenv(OPT_IN_ENV_VAR, raising=False)
    assert is_live_testing_opted_in() is False


def test_opt_in_enabled_values(monkeypatch):
    """Verify truthy values enable the opt-in flag."""
    for truthy in ("true", "TRUE", "1", "yes", "True"):
        monkeypatch.setenv(OPT_IN_ENV_VAR, truthy)
        assert is_live_testing_opted_in() is True


def test_opt_in_falsy_values(monkeypatch):
    """Verify falsy or empty values disable the opt-in flag."""
    for falsy in ("", "false", "0", "no", "anything_else"):
        monkeypatch.setenv(OPT_IN_ENV_VAR, falsy)
        assert is_live_testing_opted_in() is False


# =============================================================================
# 2. PRE-FLIGHT SAFETY GUARDRAILS VALIDATION TESTS
# =============================================================================

def test_validate_staging_target_safety_passes_valid_parameters(monkeypatch):
    """Verify validation succeeds when all parameters strictly match staging requirements."""
    monkeypatch.setenv(OPT_IN_ENV_VAR, "true")
    monkeypatch.setenv("DATABASE_BACKEND", "mongodb")

    # Should not raise
    validate_staging_target_safety(
        project_id="chainvault-staging",
        database_id="(default)",
        emulator_host=None,
        active_backend="mongodb"
    )


def test_validate_staging_target_safety_fails_without_opt_in(monkeypatch):
    """Verify validation fails immediately if opt-in is absent."""
    monkeypatch.delenv(OPT_IN_ENV_VAR, raising=False)
    with pytest.raises(StagingSafetyViolation) as exc_info:
        validate_staging_target_safety(
            project_id="chainvault-staging",
            database_id="(default)",
            emulator_host=None,
            active_backend="mongodb"
        )
    assert "require explicit opt-in" in str(exc_info.value)


def test_validate_staging_target_safety_rejects_wrong_project(monkeypatch):
    """Verify validation rejects any non-staging project ID."""
    monkeypatch.setenv(OPT_IN_ENV_VAR, "true")
    for wrong_project in ("chainvault-prod", "my-personal-gcp", "production", "default"):
        with pytest.raises(StagingSafetyViolation) as exc_info:
            validate_staging_target_safety(
                project_id=wrong_project,
                database_id="(default)",
                emulator_host=None,
                active_backend="mongodb"
            )
        assert "does not match required staging project" in str(exc_info.value)


def test_validate_staging_target_safety_rejects_wrong_database(monkeypatch):
    """Verify validation rejects any non-(default) database ID."""
    monkeypatch.setenv(OPT_IN_ENV_VAR, "true")
    for wrong_db in ("prod-db", "staging-db", "test"):
        with pytest.raises(StagingSafetyViolation) as exc_info:
            validate_staging_target_safety(
                project_id="chainvault-staging",
                database_id=wrong_db,
                emulator_host=None,
                active_backend="mongodb"
            )
        assert "does not match required database" in str(exc_info.value)


def test_validate_staging_target_safety_rejects_active_emulator(monkeypatch):
    """Verify validation rejects running if emulator host is active."""
    monkeypatch.setenv(OPT_IN_ENV_VAR, "true")
    with pytest.raises(StagingSafetyViolation) as exc_info:
        validate_staging_target_safety(
            project_id="chainvault-staging",
            database_id="(default)",
            emulator_host="127.0.0.1:8080",
            active_backend="mongodb"
        )
    assert "FIRESTORE_EMULATOR_HOST is set" in str(exc_info.value)


def test_validate_staging_target_safety_rejects_non_mongodb_backend(monkeypatch):
    """Verify validation rejects if application active backend is switched away from mongodb."""
    monkeypatch.setenv(OPT_IN_ENV_VAR, "true")
    with pytest.raises(StagingSafetyViolation) as exc_info:
        validate_staging_target_safety(
            project_id="chainvault-staging",
            database_id="(default)",
            emulator_host=None,
            active_backend="firestore"
        )
    assert "It must remain 'mongodb'" in str(exc_info.value)


# =============================================================================
# 3. STAGING TEST RUN TRACKER & OWNERSHIP TESTS
# =============================================================================

def test_tracker_generates_isolated_deterministic_ids():
    """Verify tracker produces deterministic IDs namespaced by run_id."""
    tracker = StagingTestRunTracker(run_id="abc12345")
    assert tracker.run_id == "abc12345"
    assert tracker.run_marker == "STG-RUN-abc12345"

    case_id = tracker.generate_doc_id("CS-01")
    assert case_id == "STG-TEST-abc12345-CS-01"

    ev_id = tracker.generate_doc_id("EV-99")
    assert ev_id == "STG-TEST-abc12345-EV-99"


def test_tracker_prepares_payload_with_ownership_marker():
    """Verify tracker injects run marker and test metadata into raw data dictionary."""
    tracker = StagingTestRunTracker(run_id="run_xyz")
    raw_data = {"case_id": "CS-01", "title": "Test Title"}

    payload = tracker.prepare_test_payload("CS-01", raw_data)
    assert payload["case_id"] == "CS-01"
    assert payload["title"] == "Test Title"
    assert payload["_test_run_marker"] == "STG-RUN-run_xyz"
    assert payload["_test_run_id"] == "run_xyz"
    assert "_test_created_at" in payload


def test_tracker_cleanup_deletes_only_owned_documents():
    """Verify cleanup calls delete_one ONLY when the document marker matches the run marker."""
    async def _test():
        tracker = StagingTestRunTracker(run_id="run_valid")
        tracker.record_document_creation("evidence", "EV-VALID-01")

        # Mock client and adapter
        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.primary_key = "evidence_id"

        # Mock document exists and has matching marker
        mock_adapter.find_one = AsyncMock(return_value={
            "evidence_id": "EV-VALID-01",
            "_test_run_marker": "STG-RUN-run_valid"
        })
        mock_adapter.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        mock_client.__getitem__.return_value = mock_adapter

        stats = await tracker.cleanup_owned_documents(mock_client)

        assert stats["inspected"] == 1
        assert stats["deleted"] == 1
        assert stats["skipped_unowned"] == 0
        mock_adapter.delete_one.assert_awaited_once_with({"evidence_id": "EV-VALID-01"})

    import asyncio
    asyncio.run(_test())


def test_tracker_cleanup_refuses_to_delete_unowned_document():
    """
    CRITICAL SAFETY TEST: Verify cleanup REFUSES to delete a document
    if _test_run_marker is missing or belongs to a different test run.
    """
    async def _test():
        tracker = StagingTestRunTracker(run_id="run_current")
        tracker.record_document_creation("evidence", "EV-FOREIGN-01")

        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.primary_key = "evidence_id"

        # Foreign document (e.g. from prior run or real system)
        mock_adapter.find_one = AsyncMock(return_value={
            "evidence_id": "EV-FOREIGN-01",
            "_test_run_marker": "STG-RUN-different_run"
        })
        mock_adapter.delete_one = AsyncMock()
        mock_client.__getitem__.return_value = mock_adapter

        stats = await tracker.cleanup_owned_documents(mock_client)

        assert stats["inspected"] == 1
        assert stats["deleted"] == 0
        assert stats["skipped_unowned"] == 1
        mock_adapter.delete_one.assert_not_called()

    import asyncio
    asyncio.run(_test())


def test_tracker_cleanup_handles_already_deleted_document():
    """Verify cleanup gracefully handles documents that were already deleted or not found."""
    async def _test():
        tracker = StagingTestRunTracker(run_id="run_test")
        tracker.record_document_creation("cases", "CS-MISSING-01")

        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.primary_key = "case_id"
        mock_adapter.find_one = AsyncMock(return_value=None)
        mock_adapter.delete_one = AsyncMock()
        mock_client.__getitem__.return_value = mock_adapter

        stats = await tracker.cleanup_owned_documents(mock_client)

        assert stats["inspected"] == 1
        assert stats["deleted"] == 0
        assert stats["not_found"] == 1
        mock_adapter.delete_one.assert_not_called()

    import asyncio
    asyncio.run(_test())


def test_tracker_default_run_id_is_full_32char_uuid4_hex():
    """Verify default run_id generation produces a full 32-character hex UUID4 with 128-bit entropy."""
    tracker = StagingTestRunTracker()
    assert len(tracker.run_id) == 32
    # Verify valid hexadecimal representation
    int(tracker.run_id, 16)
    assert tracker.run_marker == f"STG-RUN-{tracker.run_id}"

    # Collision test across 1000 generated run IDs
    generated_ids = {StagingTestRunTracker().run_id for _ in range(1000)}
    assert len(generated_ids) == 1000


def test_tracker_pre_registration_tracks_and_cleans_up():
    """Verify pre-registered documents are cleaned up even if subsequent logic raises an error."""
    async def _test():
        tracker = StagingTestRunTracker()
        doc_id = tracker.generate_doc_id("CS-PREREG-01")

        # 1. Pre-register before insert
        tracker.record_document_creation("cases", doc_id)
        assert ("cases", doc_id) in tracker._created_docs

        # 2. Mock adapter where doc was stored
        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.primary_key = "case_id"
        mock_adapter.find_one = AsyncMock(return_value={
            "case_id": doc_id,
            "_test_run_marker": tracker.run_marker
        })
        mock_adapter.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        mock_client.__getitem__.return_value = mock_adapter

        # 3. Cleanup successfully deletes the pre-registered document
        stats = await tracker.cleanup_owned_documents(mock_client)
        assert stats["inspected"] == 1
        assert stats["deleted"] == 1
        assert stats["not_found"] == 0

    import asyncio
    asyncio.run(_test())


def test_tracker_pre_registration_handles_aborted_write():
    """Verify pre-registered document that never reached the database is handled gracefully."""
    async def _test():
        tracker = StagingTestRunTracker()
        doc_id = tracker.generate_doc_id("CS-ABORTED-01")

        # Pre-registered, but write aborted/failed (doc never created)
        tracker.record_document_creation("cases", doc_id)

        mock_client = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.primary_key = "case_id"
        mock_adapter.find_one = AsyncMock(return_value=None)
        mock_adapter.delete_one = AsyncMock()
        mock_client.__getitem__.return_value = mock_adapter

        stats = await tracker.cleanup_owned_documents(mock_client)
        assert stats["inspected"] == 1
        assert stats["deleted"] == 0
        assert stats["not_found"] == 1
        mock_adapter.delete_one.assert_not_called()

    import asyncio
    asyncio.run(_test())


def test_tracker_cleanup_via_atomic_transaction_when_available():
    """Verify cleanup uses atomic transaction if client.firestore_client is available."""
    async def _test():
        tracker = StagingTestRunTracker(run_id="run_atomic")
        doc_id = tracker.generate_doc_id("EV-ATOMIC-01")
        tracker.record_document_creation("evidence", doc_id)

        # Mock Firestore AsyncClient with transaction support
        mock_client = MagicMock()
        mock_fs_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "evidence_id": doc_id,
            "_test_run_marker": tracker.run_marker
        }
        mock_doc_ref.get = AsyncMock(return_value=mock_snapshot)
        mock_fs_client.collection.return_value.document.return_value = mock_doc_ref

        # Mock transaction conforming to AsyncTransaction lifecycle
        mock_txn = MagicMock()
        mock_txn._clean_up = MagicMock()
        mock_txn._begin = AsyncMock()
        mock_txn._commit = AsyncMock()
        mock_txn._rollback = AsyncMock()
        mock_txn._read_only = False
        mock_txn._id = b"test_txn_id"
        mock_txn._max_attempts = 1
        mock_txn.delete = MagicMock()

        mock_fs_client.transaction.return_value = mock_txn
        mock_client.firestore_client = mock_fs_client

        stats = await tracker.cleanup_owned_documents(mock_client)

        assert stats["inspected"] == 1
        assert stats["deleted"] == 1
        mock_txn.delete.assert_called_once_with(mock_doc_ref)

    import asyncio
    asyncio.run(_test())



def test_tracker_temporary_file_isolation_and_teardown():
    """Verify temporary synthetic files are created in isolated temp directory and cleaned up."""
    tracker = StagingTestRunTracker(run_id="run_files")
    temp_dir = tracker.temp_dir_path
    assert temp_dir.exists()
    assert "chainvault_stg_run_files_" in temp_dir.name

    test_file = temp_dir / "test_artifact.bin"
    test_file.write_bytes(b"HELLO_WORLD_TEST")
    tracker.record_file_creation(test_file)
    assert test_file.exists()

    cleaned = tracker.cleanup_files()
    assert cleaned == 1
    assert not test_file.exists()
    assert not temp_dir.exists()


# =============================================================================
# 4. DIAGNOSTIC OUTPUT SANITIZATION TESTS
# =============================================================================

def test_sanitize_diagnostic_output_redacts_sensitive_keys():
    """Verify sensitive terms like token, secret, password, key are redacted from diagnostics."""
    raw_diagnostic = {
        "persistence_mode": "persistent",
        "jwt_secret": "my_super_secret_jwt_key_value",
        "access_token": "ya29.a0AfH6SM...",
        "blockchain_rpc_url": "https://sepolia.infura.io/v3/project123",
        "nested": {
            "private_key": "0x1234567890abcdef",
            "api_key": "AIzaSy...",
            "safe_metric": 42
        },
        "credentials_path": "/var/secrets/key.json"
    }

    sanitized = sanitize_diagnostic_output(raw_diagnostic)

    assert sanitized["persistence_mode"] == "persistent"
    assert sanitized["jwt_secret"] == "[REDACTED]"
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["credentials_path"] == "[REDACTED]"
    assert sanitized["nested"]["private_key"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["safe_metric"] == 42


# =============================================================================
# 5. ACTUAL FIRESTORE DOCUMENT ID RESOLUTION TESTS
# =============================================================================

def test_adapter_primary_key_resolutions_match_live_test_entities():
    """Verify FirestoreCollectionAdapter extracts exact STG-TEST IDs across all target collections."""
    from app.database.firestore import FirestoreCollectionAdapter

    tracker = StagingTestRunTracker(run_id="test_run_verify_keys")
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True

    targets = [
        ("cases", "CS-01", "case_id"),
        ("evidence", "EV-01", "evidence_id"),
        ("users", "USR-01", "username"),
        ("audit_logs", "EVT-01", "event_id"),
        ("reports", "REP-01", "report_id"),
        ("custody_transactions", "TX-01", "transaction_id"),
    ]

    for col_name, suffix, pk_field in targets:
        adapter = FirestoreCollectionAdapter(mock_client, col_name)
        expected_id = tracker.generate_doc_id(suffix)
        payload = tracker.prepare_test_payload(expected_id, {pk_field: expected_id})
        extracted_id = adapter._get_doc_id(payload)
        assert extracted_id == expected_id, f"Collection {col_name} failed ID resolution: {extracted_id} != {expected_id}"
        assert tracker.run_id in extracted_id
        assert extracted_id.startswith("STG-TEST-")


# =============================================================================
# 6. ASYNC EVENT LOOP LIFECYCLE TESTS
# =============================================================================

def test_staging_event_loop_preserves_single_loop_across_calls():
    """Verify get_staging_event_loop returns the same active loop and run_async reuses it."""
    import asyncio
    loop1 = get_staging_event_loop()
    assert loop1 is not None
    assert not loop1.is_closed()

    async def step1():
        return id(asyncio.get_running_loop())

    async def step2():
        return id(asyncio.get_running_loop())

    loop_id_1 = run_async(step1())
    loop_id_2 = run_async(step2())

    assert loop_id_1 == id(loop1)
    assert loop_id_2 == id(loop1)
    assert loop_id_1 == loop_id_2
    assert not loop1.is_closed()


def test_staging_event_loop_recreates_if_closed():
    """Verify get_staging_event_loop safely recreates a new loop if previous was closed."""
    loop = get_staging_event_loop()
    loop.close()
    assert loop.is_closed()

    new_loop = get_staging_event_loop()
    assert new_loop is not None
    assert not new_loop.is_closed()
    assert new_loop is not loop

    async def ping():
        return "alive"

    assert run_async(ping()) == "alive"

