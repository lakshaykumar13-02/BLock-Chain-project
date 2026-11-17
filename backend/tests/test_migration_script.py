"""
ChainVault Phase 3A — Migration Tool Test Suite
================================================
Validates:
1. Production safety guards (rejection of cloud endpoints and production project IDs).
2. Dry-run mode by default (zero writes to destination).
3. Document sanitization, datetime normalization to canonical RFC 3339, and binary stripping.
4. Deterministic primary key extraction across all 9 collections.
5. Disk file integrity verification and missing-file warning handling.
6. Canonical audit-event SHA-256 hash verification and tamper detection.
7. Idempotency on reruns (skipping identical documents).
8. Conflict detection (preventing silent overwrites of conflicting destination data).
9. Live emulator execution with synthetic fixtures.
"""

import os
import io
import json
import uuid
import socket
import hashlib
import asyncio
import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.migrate_mongo_to_firestore import (
    MongoToFirestoreMigrator,
    validate_emulator_target,
    clean_doc_for_firestore,
    extract_primary_key,
    calculate_file_sha256,
    find_document_differences,
    COLLECTION_SPECS
)
from app.services.audit_trail import calculate_canonical_event_hash


# =============================================================================
# 1. SAFETY GUARD & TARGET VALIDATION TESTS
# =============================================================================

def test_safety_guard_rejects_missing_or_cloud_hosts():
    """Verify validate_emulator_target strictly rejects unset or non-loopback hosts."""
    # 1. Unset host
    with pytest.raises(RuntimeError) as exc_info:
        validate_emulator_target(None, "chainvault-emulator")
    assert "FIRESTORE_EMULATOR_HOST is unset" in str(exc_info.value)

    # 2. Public cloud endpoint
    with pytest.raises(RuntimeError) as exc_info:
        validate_emulator_target("firestore.googleapis.com:443", "chainvault-emulator")
    assert "not a local loopback address" in str(exc_info.value)

    # 3. Non-local IP
    with pytest.raises(RuntimeError) as exc_info:
        validate_emulator_target("192.168.1.100:8080", "chainvault-emulator")
    assert "not a local loopback address" in str(exc_info.value)


def test_safety_guard_rejects_production_project_names():
    """Verify validate_emulator_target strictly rejects production project IDs."""
    prohibited_names = [
        "chainvault-prod",
        "chainvault-production",
        "live-chainvault",
        "chainvault-mainnet"
    ]
    for p_name in prohibited_names:
        with pytest.raises(RuntimeError) as exc_info:
            validate_emulator_target("127.0.0.1:8080", p_name)
        assert "prohibited keyword" in str(exc_info.value)


def test_safety_guard_accepts_valid_local_emulator():
    """Verify valid loopback host and emulator project name pass safety check."""
    validate_emulator_target("127.0.0.1:8080", "chainvault-emulator")
    validate_emulator_target("localhost:8080", "test-project")


# =============================================================================
# 2. DOCUMENT SANITIZATION & NORMALIZATION TESTS
# =============================================================================

def test_clean_doc_strips_id_and_normalizes_timestamps():
    """Verify clean_doc_for_firestore converts datetimes to RFC 3339 strings and removes _id."""
    dt = datetime.datetime(2026, 10, 24, 12, 0, 0, 123456, tzinfo=datetime.timezone.utc)
    raw_doc = {
        "_id": "6718fa1234567890abcdef12",
        "case_id": "CASE-100",
        "created_at": dt,
        "is_active": True,
        "count": 42,
        "nested": {
            "updated_at": dt,
            "title": "Nested Info"
        }
    }

    fallback_id, cleaned = clean_doc_for_firestore(raw_doc)
    assert fallback_id == "6718fa1234567890abcdef12"
    assert "_id" not in cleaned
    assert cleaned["case_id"] == "CASE-100"
    assert cleaned["created_at"] == "2026-10-24T12:00:00.123456Z"
    assert cleaned["nested"]["updated_at"] == "2026-10-24T12:00:00.123456Z"


def test_clean_doc_rejects_binary_payloads():
    """Requirement 5: Evidence binaries must not be ingested into Firestore."""
    raw_doc = {
        "evidence_id": "EV-001",
        "file_content": b"\x00\x01\x02rawbinarybytes"
    }
    with pytest.raises(TypeError) as exc_info:
        clean_doc_for_firestore(raw_doc)
    assert "Binary data detected" in str(exc_info.value)


# =============================================================================
# 3. DETERMINISTIC PRIMARY KEY EXTRACTION
# =============================================================================

def test_extract_primary_key_all_collections():
    """Verify deterministic document ID mapping matches the schema across all 9 collections."""
    # cases
    assert extract_primary_key("cases", {"case_id": "CASE-01"}) == "CASE-01"

    # evidence
    assert extract_primary_key("evidence", {"evidence_id": "EV-01"}) == "EV-01"

    # audit_logs
    assert extract_primary_key("audit_logs", {"event_id": "EVT-01"}) == "EVT-01"

    # custody_transactions
    assert extract_primary_key("custody_transactions", {"transaction_id": "TX-01"}) == "TX-01"

    # idempotency_records
    assert extract_primary_key("idempotency_records", {"idempotency_key": "IDEM-01"}) == "IDEM-01"

    # blockchain_checkpoints with fallback
    assert extract_primary_key("blockchain_checkpoints", {"checkpoint_id": "CHK-01"}) == "CHK-01"
    assert extract_primary_key("blockchain_checkpoints", {"evidence_id": "EV-01"}) == "CHK-EV-01"

    # reports
    assert extract_primary_key("reports", {"report_id": "REP-01"}) == "REP-01"

    # users with fallback
    assert extract_primary_key("users", {"username": "officer_alice"}) == "officer_alice"
    assert extract_primary_key("users", {"user_id": "USR-99"}) == "USR-99"

    # custody_logs (legacy mapped to audit_logs)
    assert extract_primary_key("custody_logs", {"event_id": "EVT-LEG"}) == "EVT-LEG"
    assert extract_primary_key("custody_logs", {"log_id": "LOG-01"}) == "LOG-01"


# =============================================================================
# 4. PHYSICAL FILE INTEGRITY & HASH VERIFICATION
# =============================================================================

def test_file_sha256_calculation_and_disk_verification(tmp_path):
    """Verify physical file hash calculation matches expectation and handles missing files."""
    test_file = tmp_path / "evidence_test.bin"
    content = b"ChainVault forensic test bytes 123456789"
    test_file.write_bytes(content)
    expected_hash = hashlib.sha256(content).hexdigest()

    # 1. Existing valid file
    assert calculate_file_sha256(str(test_file)) == expected_hash

    # 2. Non-existent file
    missing_file = tmp_path / "missing.bin"
    assert calculate_file_sha256(str(missing_file)) is None


def test_conflict_detection_diff_finder():
    """Verify find_document_differences accurately isolates diverging fields."""
    dest_doc = {"case_id": "CS-1", "title": "Old Title", "is_deleted": False}
    source_doc = {"case_id": "CS-1", "title": "New Title", "is_deleted": False}

    diffs = find_document_differences(dest_doc, source_doc)
    assert "title" in diffs
    assert diffs["title"]["destination"] == "Old Title"
    assert diffs["title"]["source"] == "New Title"
    assert "is_deleted" not in diffs


# =============================================================================
# 5. CANONICAL AUDIT HASH VERIFICATION
# =============================================================================

def test_audit_hash_verification_logic():
    """Verify canonical audit hash matching and mismatch detection."""
    timestamp_str = "2026-10-24T12:00:00.000000Z"
    event_dict = {
        "schema_version": 1,
        "event_id": "EVT-TEST-01",
        "evidence_id": "EV-01",
        "case_id": "CASE-10",
        "actor_id": "officer_1",
        "action": "EVIDENCE_COLLECTED",
        "timestamp": timestamp_str,
        "sequence_number": 1,
        "previous_event_hash": "0" * 64,
        "details": {"device": "mobile"}
    }
    canonical_hash = calculate_canonical_event_hash(event_dict)
    event_dict["event_hash"] = canonical_hash

    # Correct hash matches
    recalc = calculate_canonical_event_hash(event_dict)
    assert recalc == canonical_hash

    # Tampered event detected
    tampered = dict(event_dict)
    tampered["actor_id"] = "impostor"
    assert calculate_canonical_event_hash(tampered) != canonical_hash


# =============================================================================
# 6. DRY-RUN MODE & MOCK MIGRATION
# =============================================================================

def test_dry_run_mode_does_not_mutate_destination():
    """Verify dry-run mode gathers statistics without issuing writes to Firestore."""
    migrator = MongoToFirestoreMigrator(
        mongo_uri="mongodb://localhost:27017",
        mongo_db_name="chainvault_test",
        emulator_host="127.0.0.1:8080",
        project_id="chainvault-emulator",
        dry_run=True
    )
    assert migrator.dry_run is True

    # Mock MongoDB and Firestore collections
    mock_dest_col = MagicMock()
    mock_doc_ref = MagicMock()
    mock_dest_col.document.return_value = mock_doc_ref
    mock_doc_ref.get = AsyncMock(return_value=MagicMock(exists=False))
    mock_doc_ref.set = AsyncMock()

    stats = {
        "source_count": 1,
        "migrated_count": 0,
        "already_present_count": 0,
        "conflict_count": 0,
        "error_count": 0,
        "conflicts": [],
        "errors": [],
        "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
        "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
    }

    raw_doc = {
        "case_id": "CS-DRY-1",
        "title": "Dry Run Case",
        "is_deleted": False
    }

    async def _test():
        await migrator._process_document(raw_doc, "cases", mock_dest_col, stats)
        # In dry run, doc_ref.set must NOT be called
        mock_doc_ref.set.assert_not_called()
        assert stats["migrated_count"] == 1
        assert stats["error_count"] == 0

    asyncio.run(_test())


def test_idempotent_rerun_skips_identical_records():
    """Verify rerun against identical destination record increments already_present_count and avoids write."""
    migrator = MongoToFirestoreMigrator(
        mongo_uri="mongodb://localhost:27017",
        mongo_db_name="chainvault_test",
        emulator_host="127.0.0.1:8080",
        project_id="chainvault-emulator",
        dry_run=False
    )

    mock_dest_col = MagicMock()
    mock_doc_ref = MagicMock()
    mock_dest_col.document.return_value = mock_doc_ref

    # Existing document with identical content
    existing_content = {"case_id": "CS-EXIST-1", "title": "Existing Case", "is_deleted": False}
    mock_doc_ref.get = AsyncMock(return_value=MagicMock(exists=True, to_dict=lambda: existing_content))
    mock_doc_ref.set = AsyncMock()

    stats = {
        "source_count": 1,
        "migrated_count": 0,
        "already_present_count": 0,
        "conflict_count": 0,
        "error_count": 0,
        "conflicts": [],
        "errors": [],
        "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
        "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
    }

    raw_doc = dict(existing_content)

    async def _test():
        await migrator._process_document(raw_doc, "cases", mock_dest_col, stats)
        mock_doc_ref.set.assert_not_called()
        assert stats["already_present_count"] == 1
        assert stats["migrated_count"] == 0
        assert stats["conflict_count"] == 0

    asyncio.run(_test())


def test_conflict_detection_prevents_silent_overwrite():
    """Verify differing destination record increments conflict_count and aborts write."""
    migrator = MongoToFirestoreMigrator(
        mongo_uri="mongodb://localhost:27017",
        mongo_db_name="chainvault_test",
        emulator_host="127.0.0.1:8080",
        project_id="chainvault-emulator",
        dry_run=False
    )

    mock_dest_col = MagicMock()
    mock_doc_ref = MagicMock()
    mock_dest_col.document.return_value = mock_doc_ref

    # Existing document with different title
    dest_content = {"case_id": "CS-CONFLICT", "title": "Destination Title", "is_deleted": False}
    mock_doc_ref.get = AsyncMock(return_value=MagicMock(exists=True, to_dict=lambda: dest_content))
    mock_doc_ref.set = AsyncMock()

    stats = {
        "source_count": 1,
        "migrated_count": 0,
        "already_present_count": 0,
        "conflict_count": 0,
        "error_count": 0,
        "conflicts": [],
        "errors": [],
        "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
        "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
    }

    source_doc = {"case_id": "CS-CONFLICT", "title": "Incoming Source Title", "is_deleted": False}

    async def _test():
        await migrator._process_document(source_doc, "cases", mock_dest_col, stats)
        # Must NOT overwrite!
        mock_doc_ref.set.assert_not_called()
        assert stats["conflict_count"] == 1
        assert len(stats["conflicts"]) == 1
        assert stats["conflicts"][0]["diff"]["title"]["destination"] == "Destination Title"
        assert stats["conflicts"][0]["diff"]["title"]["source"] == "Incoming Source Title"

    asyncio.run(_test())


# =============================================================================
# 7. LIVE EMULATOR INTEGRATION TESTS (SYNTHETIC FIXTURES ONLY)
# =============================================================================

def is_emulator_listening(host_str="127.0.0.1:8080") -> bool:
    try:
        parts = host_str.split(":")
        with socket.create_connection((parts[0], int(parts[1])), timeout=0.2):
            return True
    except Exception:
        return False


EMU_ONLINE = is_emulator_listening("127.0.0.1:8080")


@pytest.mark.skipif(not EMU_ONLINE, reason="BLOCKED: Firestore Emulator is not running on 127.0.0.1:8080.")
def test_live_emulator_migration_lifecycle_synthetic(tmp_path):
    """
    Exercise the migration pipeline against the live Firestore Emulator
    using purely synthetic test data.
    """
    async def _run():
        migrator = MongoToFirestoreMigrator(
            mongo_uri="mongodb://localhost:27017",
            mongo_db_name="synthetic_test_db",
            emulator_host="127.0.0.1:8080",
            project_id="chainvault-emulator",
            dry_run=False
        )
        await migrator.connect()

        # Create synthetic PDF report on disk
        synthetic_pdf = tmp_path / "forensic_synth.pdf"
        pdf_bytes = b"%PDF-1.4 synthetic migration report content"
        synthetic_pdf.write_bytes(pdf_bytes)
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        # Synthetic test documents
        cid = f"CS-MIG-{uuid.uuid4().hex[:6]}"
        eid = f"EV-MIG-{uuid.uuid4().hex[:6]}"
        rid = f"REP-MIG-{uuid.uuid4().hex[:6]}"
        evt_id = f"EVT-MIG-{uuid.uuid4().hex[:6]}"

        timestamp_str = "2026-10-24T12:30:00.000000Z"
        audit_payload = {
            "schema_version": 1,
            "event_id": evt_id,
            "evidence_id": eid,
            "case_id": cid,
            "actor_id": "investigator_synthetic",
            "action": "EVIDENCE_COLLECTED",
            "timestamp": timestamp_str,
            "sequence_number": 1,
            "previous_event_hash": "0" * 64,
            "details": {"type": "usb_drive"}
        }
        canonical_h = calculate_canonical_event_hash(audit_payload)
        audit_payload["event_hash"] = canonical_h

        # 1. Process Case document
        case_stats = {
            "source_count": 1, "migrated_count": 0, "already_present_count": 0,
            "conflict_count": 0, "error_count": 0, "conflicts": [], "errors": [],
            "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
            "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
        }
        dest_cases = migrator._firestore_client.collection("cases")
        await migrator._process_document({"case_id": cid, "title": "Migrated Case", "is_deleted": False}, "cases", dest_cases, case_stats)
        assert case_stats["migrated_count"] == 1

        # 2. Process Evidence document with physical file verification
        dest_ev = migrator._firestore_client.collection("evidence")
        ev_stats = {
            "source_count": 1, "migrated_count": 0, "already_present_count": 0,
            "conflict_count": 0, "error_count": 0, "conflicts": [], "errors": [],
            "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
            "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
        }
        ev_doc = {
            "evidence_id": eid,
            "case_id": cid,
            "file_path": str(synthetic_pdf),
            "file_hash": pdf_sha256,
            "file_size": len(pdf_bytes),
            "custody_version": 1
        }
        await migrator._process_document(ev_doc, "evidence", dest_ev, ev_stats)
        assert ev_stats["migrated_count"] == 1
        assert ev_stats["file_checks"]["verified_on_disk"] == 1

        # 3. Process Audit Log document with canonical hash check
        dest_audit = migrator._firestore_client.collection("audit_logs")
        audit_stats = {
            "source_count": 1, "migrated_count": 0, "already_present_count": 0,
            "conflict_count": 0, "error_count": 0, "conflicts": [], "errors": [],
            "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
            "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
        }
        await migrator._process_document(audit_payload, "audit_logs", dest_audit, audit_stats)
        assert audit_stats["migrated_count"] == 1
        assert audit_stats["hash_verification"]["verified"] == 1

        # 4. Read back from emulator to confirm persistence
        snap_case = await dest_cases.document(cid).get()
        assert snap_case.exists
        assert snap_case.to_dict()["title"] == "Migrated Case"

        snap_ev = await dest_ev.document(eid).get()
        assert snap_ev.exists
        assert snap_ev.to_dict()["file_hash"] == pdf_sha256

        snap_audit = await dest_audit.document(evt_id).get()
        assert snap_audit.exists
        assert snap_audit.to_dict()["event_hash"] == canonical_h

        # 5. Cleanup synthetic test records from emulator
        await dest_cases.document(cid).delete()
        await dest_ev.document(eid).delete()
        await dest_audit.document(evt_id).delete()

        await migrator.close()

    asyncio.run(_run())
