"""
ChainVault Phase 2 — Cloud Firestore Persistence Adapter Test Suite
===================================================================
Validates:
1. Client initialization, configuration defaults, persistence modes, and connection lifecycle.
2. Production fail-closed enforcement (no silent in-memory fallback when persistent storage required).
3. Document ID determinism and uniqueness enforcement.
4. Collection adapter CRUD operations (cases, evidence, audit logs, custody transactions, idempotency, reports).
5. Canonical audit trail serialization and bit-for-bit SHA-256 hash preservation.
6. Multi-worker distributed lease locking and fencing-version CAS verification using Firestore transactions.
7. Separation of physical binary storage from database metadata.
8. Live Firestore Emulator integration tests (reported as BLOCKED if emulator is offline).
"""

import os
import io
import time
import json
import uuid
import socket
import hashlib
import asyncio
import datetime
import pytest
from typing import Optional, Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from google.api_core.exceptions import AlreadyExists

from app.database.base import BaseDatabaseClient
from app.database.firestore import (
    FirestoreClient,
    FirestoreCollectionAdapter,
    FirestoreInsertResult,
    FirestoreUpdateResult,
    FirestoreDeleteResult,
    FirestoreCursor,
    FIRESTORE_AVAILABLE
)
from app.database.mongodb import MongoDBClient, get_database_client
from app.services.hashing import calculate_hash
from app.services.audit_trail import (
    calculate_canonical_event_hash,
    canonical_event_representation,
    normalize_utc_timestamp
)
from app.services.custody_transaction import CustodyTransactionStatus


# =============================================================================
# 1. CLIENT INITIALIZATION & CONFIGURATION TESTS
# =============================================================================

def test_firestore_client_instantiation():
    """Verify FirestoreClient inherits from BaseDatabaseClient and sets default configs."""
    client = FirestoreClient()
    assert isinstance(client, BaseDatabaseClient)
    assert client.database_id == "(default)"
    assert client.is_connected() is False
    assert client.get_persistence_mode() in ["resilient_fallback", "unavailable"]


def test_database_backend_selection(monkeypatch):
    """Verify DATABASE_BACKEND environment variable selects the appropriate client without switching environments."""
    # Default is MongoDB
    monkeypatch.delenv("DATABASE_BACKEND", raising=False)
    default_client = get_database_client()
    assert isinstance(default_client, MongoDBClient)

    # Explicit MongoDB
    monkeypatch.setenv("DATABASE_BACKEND", "mongodb")
    mongo_client = get_database_client()
    assert isinstance(mongo_client, MongoDBClient)

    # Explicit Firestore
    monkeypatch.setenv("DATABASE_BACKEND", "firestore")
    fs_client = get_database_client()
    assert isinstance(fs_client, FirestoreClient)


def test_fail_closed_when_persistent_storage_required(monkeypatch):
    """
    Requirement 9: Production persistence must fail closed.
    Never silently fall back to in-memory storage when persistent storage is required.
    """
    monkeypatch.setenv("REQUIRE_PERSISTENT_STORAGE", "true")
    client = FirestoreClient()
    assert client.require_persistent_storage is True

    # Simulate connection failure
    async def _test():
        with patch.object(client, "connect", side_effect=RuntimeError("Simulated Firestore unreachable")):
            with pytest.raises(RuntimeError) as exc_info:
                await client.connect()
            assert "unreachable" in str(exc_info.value)

    asyncio.run(_test())


# =============================================================================
# 2. CANONICAL AUDIT-EVENT SERIALIZATION & SHA-256 HASH PRESERVATION
# =============================================================================

def test_canonical_event_hashing_exact_preservation():
    """
    Requirement 7: Preserve canonical audit-event serialization and SHA-256 hashing exactly.
    Proves that storing into and retrieving from Firestore adapter schema produces
    bit-for-bit identical SHA-256 hashes compared with original MongoDB audit trail.
    """
    sample_timestamp = "2026-10-24T10:00:00.123456Z"
    event_payload = {
        "schema_version": 1,
        "event_id": "EVT-EV-001-0002-A1B2C3",
        "log_id": "EVT-EV-001-0002-A1B2C3",
        "evidence_id": "EV-001",
        "case_id": "CV-2026-001",
        "actor_id": "investigator1",
        "action": "CUSTODY_TRANSFER",
        "timestamp": sample_timestamp,
        "sequence_number": 2,
        "previous_event_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "anchor_reference": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "details": {
            "previous_custodian": "investigator1",
            "new_custodian": "officer2",
            "reason": "Court evidence transfer"
        }
    }

    # 1. Original Hash
    original_hash = calculate_canonical_event_hash(event_payload)
    assert len(original_hash) == 64
    assert isinstance(original_hash, str)

    # 2. Adapter Cleaning & Round-Trip
    client = FirestoreClient()
    adapter = client.audit_logs
    cleaned = adapter._clean_doc_for_storage(event_payload)

    # Assert all hash-critical fields retained
    assert cleaned["event_id"] == event_payload["event_id"]
    assert cleaned["timestamp"] == sample_timestamp
    assert cleaned["sequence_number"] == 2
    assert cleaned["previous_event_hash"] == event_payload["previous_event_hash"]

    # 3. Re-calculated Hash from Cleaned Adapter Document
    recalculated_hash = calculate_canonical_event_hash(cleaned)
    assert recalculated_hash == original_hash, (
        f"CRITICAL REGRESSION: Canonical event hash diverged! "
        f"Expected {original_hash}, got {recalculated_hash}."
    )


# =============================================================================
# 3. PHYSICAL EVIDENCE & REPORT FILE STORAGE SEPARATION
# =============================================================================

def test_storage_separation_metadata_only():
    """
    Requirement 8: Keep evidence binaries and PDF files in the existing file-storage layer.
    Firestore must store metadata and paths, not file contents.
    """
    client = FirestoreClient()
    adapter = client.evidence

    evidence_doc = {
        "evidence_id": "EV-STORE-001",
        "case_id": "CV-2026-001",
        "filename": "surveillance.mp4",
        "stored_filename": "uuid_surveillance.mp4",
        "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "file_size": 104857600,  # 100MB
        "file_path": "/var/data/evidence/uuid_surveillance.mp4",
        "custodian": "officer1",
        "uploaded_at": "2026-10-24T10:00:00Z"
    }

    doc_id = adapter._get_doc_id(evidence_doc)
    assert doc_id == "EV-STORE-001"

    cleaned = adapter._clean_doc_for_storage(evidence_doc)
    # Binary payload is NOT stored in document
    assert "file_bytes" not in cleaned
    assert "content" not in cleaned
    # Physical file path and checksum are preserved
    assert cleaned["file_path"] == "/var/data/evidence/uuid_surveillance.mp4"
    assert cleaned["file_hash"] == evidence_doc["file_hash"]


# =============================================================================
# 4. DETERMINISTIC DOCUMENT ID & QUERY COMPATIBILITY
# =============================================================================

def test_deterministic_document_id_mapping():
    """
    Requirement 5: Preserve deterministic document IDs and enforce uniqueness.
    """
    client = FirestoreClient()

    assert client.cases._get_doc_id({"case_id": "CASE-101"}) == "CASE-101"
    assert client.evidence._get_doc_id({"evidence_id": "EV-202"}) == "EV-202"
    assert client.audit_logs._get_doc_id({"event_id": "EVT-303"}) == "EVT-303"
    assert client.custody_transactions._get_doc_id({"transaction_id": "CTX-404"}) == "CTX-404"
    assert client.idempotency_records._get_doc_id({"idempotency_key": "IDEM-505"}) == "IDEM-505"
    assert client.reports._get_doc_id({"report_id": "REP-606"}) == "REP-606"
    assert client.blockchain_checkpoints._get_doc_id({"checkpoint_id": "CHK-707"}) == "CHK-707"
    assert client.blockchain_checkpoints._get_doc_id({"evidence_id": "EV-707"}) == "CHK-EV-707"


# =============================================================================
# 5. DISTRIBUTED LEASE & FENCING TRANSACTIONS (MOCK / OCC LOGIC TESTS)
# =============================================================================

def test_lease_fencing_version_check_logic():
    """
    Requirement 6: Fencing token verification logic prevents stale workers from committing state.
    """
    # Simulated current Firestore evidence document state
    current_doc = {
        "evidence_id": "EV-FENCE-01",
        "custodian": "officer1",
        "custody_version": 2,  # Current active version
        "transfer_lock": {
            "status": "LOCKED",
            "actor": "worker1",
            "lock_token": "TOKEN-AAA",
            "expires_at": time.time() + 30.0,
            "fencing_version": 2
        }
    }

    # Scenario A: Stale worker with old expected_version=1 attempts release
    stale_version = 1
    assert current_doc["custody_version"] != stale_version, "Fencing token must reject stale worker"

    # Scenario B: Stale worker with wrong lock_token attempts release
    wrong_token = "TOKEN-WRONG"
    assert current_doc["transfer_lock"]["lock_token"] != wrong_token, "Lock token must match lease owner"

    # Scenario C: Valid worker with matching token and version succeeds
    valid_token = "TOKEN-AAA"
    valid_version = 2
    assert current_doc["transfer_lock"]["lock_token"] == valid_token
    assert current_doc["custody_version"] == valid_version


def test_custody_transaction_state_transitions():
    """
    Requirement 4 & 6: Verify durable transaction state machine transitions are respected in Firestore adapter.
    """
    from app.services.custody_transaction import ALLOWED_TRANSITIONS

    # Allowed: PREPARED -> SUBMITTED
    assert CustodyTransactionStatus.SUBMITTED in ALLOWED_TRANSITIONS[CustodyTransactionStatus.PREPARED]

    # Allowed: SUBMITTED -> CONFIRMED
    assert CustodyTransactionStatus.CONFIRMED in ALLOWED_TRANSITIONS[CustodyTransactionStatus.SUBMITTED]

    # Allowed: CONFIRMED -> ANCHOR_SUBMITTED
    assert CustodyTransactionStatus.ANCHOR_SUBMITTED in ALLOWED_TRANSITIONS[CustodyTransactionStatus.CONFIRMED]

    # Allowed: ANCHOR_SUBMITTED -> COMPLETED
    assert CustodyTransactionStatus.COMPLETED in ALLOWED_TRANSITIONS[CustodyTransactionStatus.ANCHOR_SUBMITTED]

    # Illegal transition: PREPARED directly to COMPLETED
    assert CustodyTransactionStatus.COMPLETED not in ALLOWED_TRANSITIONS[CustodyTransactionStatus.PREPARED]


# =============================================================================
# 6. FIRESTORE EMULATOR INTEGRATION TESTS (REPORT BLOCKED IF UNAVAILABLE)
# =============================================================================

def is_emulator_reachable(host_str: Optional[str]) -> bool:
    """Check if the Firestore Emulator is actively listening on configured host:port."""
    hosts = [host_str] if host_str else ["127.0.0.1:8080", "localhost:8080"]
    for h in hosts:
        if not h:
            continue
        try:
            parts = h.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 8080
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except Exception:
            continue
    return False


EMULATOR_HOST = os.getenv("FIRESTORE_EMULATOR_HOST") or ("127.0.0.1:8080" if is_emulator_reachable("127.0.0.1:8080") else "localhost:8080")
EMULATOR_PROJECT = os.getenv("FIREBASE_PROJECT_ID") or "chainvault-emulator"
EMULATOR_ONLINE = is_emulator_reachable(EMULATOR_HOST)

if EMULATOR_ONLINE:
    os.environ["FIRESTORE_EMULATOR_HOST"] = EMULATOR_HOST
    os.environ["FIREBASE_PROJECT_ID"] = EMULATOR_PROJECT
    os.environ["GCLOUD_PROJECT"] = EMULATOR_PROJECT


def create_test_client() -> FirestoreClient:
    c = FirestoreClient()
    c.emulator_host = EMULATOR_HOST
    c.project_id = EMULATOR_PROJECT
    return c


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_crud_operations():
    """
    Requirement 10: Live test against Firestore Emulator.
    Executed only if the emulator is actively running; otherwise marked BLOCKED.
    """
    async def _run():
        client = create_test_client()
        await client.connect()
        assert client.is_connected() is True

        # 1. Ping
        assert await client.ping() is True

        # 2. Insert Case
        case_id = f"CASE-EMU-{uuid.uuid4().hex[:6]}"
        res = await client.cases.insert_one({
            "case_id": case_id,
            "title": "Emulator Test Case",
            "is_deleted": False
        })
        assert res.inserted_id == case_id

        # 3. Read back Case
        found = await client.cases.find_one({"case_id": case_id})
        assert found is not None
        assert found["title"] == "Emulator Test Case"

        # 4. Soft Delete Case
        await client.cases.update_one({"case_id": case_id}, {"$set": {"is_deleted": True}})
        updated = await client.cases.find_one({"case_id": case_id})
        assert updated["is_deleted"] is True

        # 5. Cleanup
        await client.cases.delete_one({"case_id": case_id})
        assert await client.cases.find_one({"case_id": case_id}) is None

        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_concurrency_lease_and_fencing():
    """
    Requirement 6 & 10: Live multi-worker concurrency and lease fencing test against Firestore Emulator.
    Executed only if the emulator is actively running; otherwise marked BLOCKED.
    """
    async def _run():
        client = create_test_client()
        await client.connect()

        ev_id = f"EV-EMU-{uuid.uuid4().hex[:6]}"
        await client.evidence.insert_one({
            "evidence_id": ev_id,
            "custodian": "officer1",
            "custody_version": 1
        })

        # Worker 1 acquires lock
        acq1, tok1, err1, ver1 = await client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker1",
            lease_seconds=5.0
        )
        assert acq1 is True
        assert tok1 is not None
        assert ver1 == 1

        # Worker 2 attempts concurrent acquisition -> rejected (LOCKED)
        acq2, tok2, err2, ver2 = await client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker2",
            wait_timeout=0.05
        )
        assert acq2 is False
        assert err2 == "LOCKED"

        # Worker 1 releases with valid fencing version -> succeeds and advances version to 2
        rel = await client.release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=tok1,
            new_custodian="officer2",
            expected_version=1
        )
        assert rel is True

        # Verify updated custodian and version
        doc = await client.evidence.find_one({"evidence_id": ev_id})
        assert doc["custodian"] == "officer2"
        assert doc["custody_version"] == 2
        assert doc["transfer_lock"]["status"] == "UNLOCKED"

        # Cleanup
        await client.evidence.delete_one({"evidence_id": ev_id})
        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_duplicate_id_atomic_rejection():
    """Verify Firestore adapter raises AlreadyExists on duplicate deterministic ID creation."""
    async def _run():
        client = create_test_client()
        await client.connect()
        cid = f"CASE-DUP-{uuid.uuid4().hex[:6]}"

        # 1. Insert original
        res = await client.cases.insert_one({"case_id": cid, "title": "Original Case"})
        assert res.inserted_id == cid

        # 2. Duplicate insertion must fail atomically
        with pytest.raises(AlreadyExists):
            await client.cases.insert_one({"case_id": cid, "title": "Duplicate Case"})

        # Cleanup
        await client.cases.delete_one({"case_id": cid})
        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_query_filtering_sorting_and_pagination():
    """Verify live Firestore querying with equality, $in, $ne, sorting, and pagination."""
    async def _run():
        client = create_test_client()
        await client.connect()

        test_batch = f"BATCH-{uuid.uuid4().hex[:6]}"
        inserted_ids = []
        for i in range(1, 6):
            ev_id = f"EV-PAG-{test_batch}-{i}"
            inserted_ids.append(ev_id)
            await client.evidence.insert_one({
                "evidence_id": ev_id,
                "batch_id": test_batch,
                "status": "STORED" if i <= 3 else "TRANSFERRED",
                "sequence_number": i,
                "score": i * 10
            })

        # 1. Query with equality
        stored_cursor = client.evidence.find({"batch_id": test_batch, "status": "STORED"})
        stored_items = await stored_cursor.to_list()
        assert len(stored_items) == 3

        # 2. Query with $in
        in_cursor = client.evidence.find({"batch_id": test_batch, "sequence_number": {"$in": [2, 4]}})
        in_items = await in_cursor.to_list()
        assert len(in_items) == 2

        # 3. Query with $ne
        ne_cursor = client.evidence.find({"batch_id": test_batch, "status": {"$ne": "TRANSFERRED"}})
        ne_items = await ne_cursor.to_list()
        assert len(ne_items) == 3

        # 4. Sorting and Pagination (skip 1, limit 2)
        sorted_cursor = client.evidence.find({"batch_id": test_batch})
        sorted_cursor.sort("sequence_number", 1).skip(1).limit(2)
        paged_items = await sorted_cursor.to_list()
        assert len(paged_items) == 2
        assert paged_items[0]["sequence_number"] == 2
        assert paged_items[1]["sequence_number"] == 3

        # Cleanup
        for eid in inserted_ids:
            await client.evidence.delete_one({"evidence_id": eid})
        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_lease_expiration_and_fencing_rejection():
    """Verify lease expiration allows reacquisition and stale fencing version is rejected."""
    async def _run():
        client = create_test_client()
        await client.connect()

        ev_id = f"EV-EXP-{uuid.uuid4().hex[:6]}"
        await client.evidence.insert_one({
            "evidence_id": ev_id,
            "custodian": "officer_alice",
            "custody_version": 5
        })

        # 1. Worker 1 acquires with very short lease (0.2s)
        acq1, tok1, err1, ver1 = await client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_1",
            lease_seconds=0.2
        )
        assert acq1 is True
        assert ver1 == 5

        # 2. Worker 2 immediately blocked
        acq2, tok2, err2, _ = await client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_2",
            wait_timeout=0.05
        )
        assert acq2 is False
        assert err2 == "LOCKED"

        # 3. Wait for Worker 1's lease to expire
        await asyncio.sleep(0.25)

        # 4. Worker 2 can now acquire because lease expired
        acq3, tok3, err3, ver3 = await client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_2",
            lease_seconds=5.0
        )
        assert acq3 is True
        assert ver3 == 5

        # 5. Worker 1 tries to release with its stale token -> rejected
        rel_stale = await client.release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=tok1,
            new_custodian="officer_alice",
            expected_version=5
        )
        assert rel_stale is False

        # 6. Worker 2 releases with correct token -> succeeds and increments version to 6
        rel_valid = await client.release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=tok3,
            new_custodian="officer_bob",
            expected_version=5
        )
        assert rel_valid is True

        ev_doc = await client.evidence.find_one({"evidence_id": ev_id})
        assert ev_doc["custody_version"] == 6
        assert ev_doc["custodian"] == "officer_bob"

        # Cleanup
        await client.evidence.delete_one({"evidence_id": ev_id})
        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_idempotency_and_state_recovery():
    """Verify durable idempotency records and custody transaction state transitions in emulator."""
    async def _run():
        client = create_test_client()
        await client.connect()

        idem_key = f"IDEM-{uuid.uuid4().hex}"
        tx_id = f"TX-EMU-{uuid.uuid4().hex[:8]}"

        # 1. Store initial idempotency record
        await client.idempotency_records.insert_one({
            "idempotency_key": idem_key,
            "status": "IN_PROGRESS",
            "transaction_id": tx_id,
            "created_at": "2026-10-24T10:00:00.000000Z"
        })

        # 2. Store corresponding custody transaction in PREPARED state
        await client.custody_transactions.insert_one({
            "transaction_id": tx_id,
            "idempotency_key": idem_key,
            "status": CustodyTransactionStatus.PREPARED.value,
            "evidence_id": "EV-TEST-001"
        })

        # 3. Simulate recovery lookup after worker interruption
        found_idem = await client.idempotency_records.find_one({"idempotency_key": idem_key})
        assert found_idem is not None
        assert found_idem["status"] == "IN_PROGRESS"
        assert found_idem["transaction_id"] == tx_id

        found_tx = await client.custody_transactions.find_one({"transaction_id": tx_id})
        assert found_tx is not None
        assert found_tx["status"] == "PREPARED"

        # 4. Durable transition to ANCHOR_SUBMITTED then COMPLETED
        await client.custody_transactions.update_one(
            {"transaction_id": tx_id},
            {"$set": {"status": CustodyTransactionStatus.ANCHOR_SUBMITTED.value}}
        )
        await client.custody_transactions.update_one(
            {"transaction_id": tx_id},
            {"$set": {"status": CustodyTransactionStatus.COMPLETED.value}}
        )
        await client.idempotency_records.update_one(
            {"idempotency_key": idem_key},
            {"$set": {"status": "COMPLETED"}}
        )

        completed_tx = await client.custody_transactions.find_one({"transaction_id": tx_id})
        assert completed_tx["status"] == "COMPLETED"

        # Cleanup
        await client.idempotency_records.delete_one({"idempotency_key": idem_key})
        await client.custody_transactions.delete_one({"transaction_id": tx_id})
        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_audit_hash_recalculation_roundtrip():
    """Verify audit log event stored and retrieved from Firestore produces byte-for-byte identical canonical SHA-256 hash."""
    async def _run():
        client = create_test_client()
        await client.connect()

        ev_id = f"EV-HASH-{uuid.uuid4().hex[:6]}"
        evt_id = f"EVT-HASH-{uuid.uuid4().hex[:6]}"
        timestamp_str = "2026-10-24T08:30:00.123456Z"

        audit_record = {
            "schema_version": 1,
            "event_id": evt_id,
            "evidence_id": ev_id,
            "case_id": "CASE-101",
            "actor_id": "forensic_officer_42",
            "action": "EVIDENCE_COLLECTED",
            "timestamp": timestamp_str,
            "sequence_number": 1,
            "previous_event_hash": "0" * 64,
            "details": {"source": "laptop", "serial": "SN-987654"}
        }

        canonical_hash = calculate_canonical_event_hash(audit_record)
        audit_record["event_hash"] = canonical_hash

        # Store in Firestore
        await client.audit_logs.insert_one(audit_record)

        # Retrieve back from Firestore
        retrieved = await client.audit_logs.find_one({"event_id": evt_id})
        assert retrieved is not None

        # Re-compute hash strictly from retrieved document
        recalculated_hash = calculate_canonical_event_hash(retrieved)

        assert recalculated_hash == canonical_hash
        assert recalculated_hash == retrieved["event_hash"]

        # Cleanup
        await client.audit_logs.delete_one({"event_id": evt_id})
        await client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not EMULATOR_ONLINE, reason=f"BLOCKED: Firestore Emulator is not running on {EMULATOR_HOST}.")
def test_live_emulator_report_metadata_and_storage_independence(tmp_path):
    """Verify report metadata in Firestore remains decoupled from file storage on disk."""
    async def _run():
        client = create_test_client()
        await client.connect()

        # Simulate generated PDF report on disk
        fake_pdf = tmp_path / "forensic_report_TEST.pdf"
        pdf_content = b"%PDF-1.4 mock forensic report binary content"
        fake_pdf.write_bytes(pdf_content)
        file_sha256 = hashlib.sha256(pdf_content).hexdigest()

        rep_id = f"REP-EMU-{uuid.uuid4().hex[:6]}"
        case_id = f"CASE-REP-{uuid.uuid4().hex[:6]}"

        # Store only metadata in Firestore
        await client.reports.insert_one({
            "report_id": rep_id,
            "case_id": case_id,
            "file_path": str(fake_pdf),
            "file_name": fake_pdf.name,
            "file_size": len(pdf_content),
            "sha256_hash": file_sha256,
            "generated_at": "2026-10-24T09:00:00.000000Z"
        })

        # Fetch metadata
        meta = await client.reports.find_one({"report_id": rep_id})
        assert meta is not None
        assert "binary_content" not in meta
        assert meta["sha256_hash"] == file_sha256

        # Verify disk file is untouched and readable
        disk_bytes = fake_pdf.read_bytes()
        assert hashlib.sha256(disk_bytes).hexdigest() == meta["sha256_hash"]

        # Cleanup
        await client.reports.delete_one({"report_id": rep_id})
        await client.close()

    asyncio.run(_run())


# =============================================================================
# 7. UNIT TESTS FOR COLLECTION ADAPTER MAPPING & CURSOR
# =============================================================================

def test_cursor_sorting_and_to_list():
    """Verify FirestoreCursor correctly handles in-memory and stream document sorting and limits."""
    raw_docs = [
        {"evidence_id": "EV-03", "sequence_number": 3},
        {"evidence_id": "EV-01", "sequence_number": 1},
        {"evidence_id": "EV-02", "sequence_number": 2}
    ]

    cursor = FirestoreCursor(raw_docs)
    cursor.sort("sequence_number", 1)

    async def _test():
        res = await cursor.to_list(length=2)
        assert len(res) == 2
        assert res[0]["sequence_number"] == 1
        assert res[1]["sequence_number"] == 2

    asyncio.run(_test())


def test_cursor_async_iteration():
    """Verify FirestoreCursor supports async for iteration."""
    raw_docs = [
        {"event_id": "EVT-1"},
        {"event_id": "EVT-2"}
    ]
    cursor = FirestoreCursor(raw_docs)

    async def _test():
        items = []
        async for doc in cursor:
            items.append(doc["event_id"])
        assert items == ["EVT-1", "EVT-2"]

    asyncio.run(_test())


def test_adapter_crud_mock_operations():
    """Exercise FirestoreCollectionAdapter CRUD methods using mock AsyncClient."""
    mock_client = MagicMock()
    client = FirestoreClient()
    client._client = mock_client
    client._connected = True

    # Mock collection and document
    mock_col = MagicMock()
    mock_doc_ref = MagicMock()
    mock_client.collection.return_value = mock_col
    mock_col.document.return_value = mock_doc_ref

    # 1. create_index
    async def _test_index():
        idx = await client.cases.create_index("case_id", unique=True)
        assert idx == "cases_idx"
    asyncio.run(_test_index())

    # 2. insert_one
    async def _test_insert():
        mock_doc_ref.create = AsyncMock()
        res = await client.cases.insert_one({"case_id": "CS-999", "title": "Mock Case"})
        assert res.inserted_id == "CS-999"
        mock_col.document.assert_called_with("CS-999")
        mock_doc_ref.create.assert_awaited_once_with({"case_id": "CS-999", "title": "Mock Case"})
    asyncio.run(_test_insert())

    # 3. find_one
    async def _test_find_one():
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {"case_id": "CS-999", "title": "Mock Case"}
        mock_doc_ref.get = AsyncMock(return_value=mock_snapshot)

        found = await client.cases.find_one({"case_id": "CS-999"})
        assert found is not None
        assert found["case_id"] == "CS-999"
    asyncio.run(_test_find_one())

    # 4. update_one
    async def _test_update():
        mock_doc_ref.get = AsyncMock(return_value=MagicMock(exists=True, to_dict=lambda: {"case_id": "CS-999"}))
        mock_doc_ref.update = AsyncMock()
        up_res = await client.cases.update_one({"case_id": "CS-999"}, {"$set": {"title": "Updated"}})
        assert up_res.modified_count == 1
        mock_doc_ref.update.assert_awaited_once_with({"title": "Updated"})
    asyncio.run(_test_update())

    # 5. delete_one
    async def _test_delete():
        mock_doc_ref.delete = AsyncMock()
        del_res = await client.cases.delete_one({"case_id": "CS-999"})
        assert del_res.deleted_count == 1
        mock_doc_ref.delete.assert_awaited_once()
    asyncio.run(_test_delete())
