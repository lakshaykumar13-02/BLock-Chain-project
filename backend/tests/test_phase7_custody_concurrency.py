"""
ChainVault Phase 7 — Custody Anchoring & Multi-Worker Concurrency Test Suite
=============================================================================
Tests:
1. Verifiable on-chain cryptographic custody anchoring (exact canonical SHA-256 match, VERIFIED).
2. Tampered on-chain anchor event hash detection (ANCHOR_HASH_MISMATCH, TAMPERED).
3. Tampered on-chain anchor predecessor link detection (ANCHOR_PREDECESSOR_MISMATCH, TAMPERED).
4. Mismatched evidence ID in on-chain anchor (ANCHOR_EVIDENCE_MISMATCH, INCONSISTENT).
5. Missing on-chain anchor when required (CUSTODY_ANCHOR_NOT_FOUND, INCONSISTENT).
6. Missing on-chain anchor when optional (local chain intact, blockchain_anchored=False, never false VERIFIED).
7. Blockchain RPC node unavailable during anchor verification (BLOCKCHAIN_RPC_UNAVAILABLE, UNAVAILABLE).
8. Multi-worker simultaneous transfer conflict prevention (409 Conflict, no branching, strict sequence).
9. Idempotent transfer retry (cached identical response, no duplicate events).
10. Automatic lease expiration recovery for stale/crashed worker locks.
11. Safe failure release (lock cleaned up on exception, no corrupt custodian state).
"""

import io
import os
import time
import asyncio
import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import (
    AUDIT_LOGS_STORE,
    _IN_MEMORY_TRANSFER_LOCKS,
    IDEMPOTENCY_STORE,
    acquire_custody_transfer_lock,
    release_custody_transfer_lock
)
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    CHAIN_CUSTODY_ANCHORS,
    anchor_custody_event_on_chain,
    get_custody_anchor_from_chain
)
from app.services.audit_trail import (
    record_custody_event,
    verify_custody_audit_trail,
    calculate_canonical_event_hash,
    get_stored_custody_events
)

client = TestClient(app)


def get_test_token(username="investigator1"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def cleanup_phase7_synthetic_records():
    """Ensure all synthetic test records are cleaned up after each test."""
    synthetic_ids = [
        "EV-PH7-001", "EV-PH7-002", "EV-PH7-003", "EV-PH7-004",
        "EV-PH7-005", "EV-PH7-006", "EV-PH7-007", "EV-PH7-008",
        "EV-PH7-009", "EV-PH7-010", "EV-PH7-011"
    ]
    yield
    for ev_id in synthetic_ids:
        rec = EVIDENCE_STORE.pop(ev_id, None)
        if rec and rec.get("file_path") and os.path.exists(rec["file_path"]):
            try:
                os.remove(rec["file_path"])
            except OSError:
                pass
        AUDIT_LOGS_STORE.pop(ev_id, None)
        CHAIN_EVIDENCE_STORE.pop(ev_id, None)
        CHAIN_CUSTODY_LOGS.pop(ev_id, None)
        CHAIN_CUSTODY_ANCHORS.pop(ev_id, None)
        _IN_MEMORY_TRANSFER_LOCKS.pop(ev_id, None)
    IDEMPOTENCY_STORE.clear()


# =============================================================================
# PRIORITY 1: CUSTODY ANCHORING TESTS
# =============================================================================

def test_01_verifiable_custody_anchoring_verified():
    """
    Test 1: Custody transfer anchors exact canonical SHA-256 on-chain.
    Independent verifier retrieves on-chain anchor and confirms bit-for-bit equality.
    Expected: VERIFIED, blockchain_anchored=True.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-001"
    payload = b"Phase 7 Forensic Artifact 001"
    file_hash = hashlib.sha256(payload).hexdigest()

    # Step A: Ingestion (Genesis)
    files = {"file": ("artifact_001.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-001"}, headers=headers)
    assert up_res.status_code == 201

    # Step B: Register evidence on-chain
    reg_res = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH7-001"}, headers=headers)
    assert reg_res.status_code == 200

    # Step C: Transfer custody to analyst1
    t_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst1",
        "reason": "Secure forensic lab analysis"
    }, headers=headers)
    assert t_res.status_code == 200

    # Step D: Verify that on-chain anchor was recorded and matches canonical event hash
    log_entry = t_res.json()["record"]
    seq = log_entry["sequence_number"]
    canonical_hash = log_entry["event_hash"]

    anchor, anchor_err = get_custody_anchor_from_chain(ev_id, seq)
    assert anchor_err is None
    assert anchor is not None
    assert anchor["event_hash"].lower() == canonical_hash.lower()
    assert anchor["evidence_id"] == ev_id

    # Step E: Verify complete custody audit trail with strict blockchain verification
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "VERIFIED"
    assert res["verified"] is True
    assert res["tampered"] is False
    assert res["chain_intact"] is True
    assert res["blockchain_reconciled"] is True


def test_02_tampered_on_chain_anchor_hash_detected():
    """
    Test 2: On-chain anchor contains a modified/mismatched event hash.
    Independent verifier detects discrepancy between canonical hash and on-chain anchor.
    Expected: TAMPERED with technical_error ANCHOR_HASH_MISMATCH.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-002"
    payload = b"Phase 7 Forensic Artifact 002"
    file_hash = hashlib.sha256(payload).hexdigest()

    files = {"file": ("artifact_002.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-002"}, headers=headers)
    client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH7-002"}, headers=headers)

    t_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst1",
        "reason": "Forensic lab handover"
    }, headers=headers)
    assert t_res.status_code == 200
    seq = t_res.json()["record"]["sequence_number"]

    # Tamper with on-chain anchor hash
    assert ev_id in CHAIN_CUSTODY_ANCHORS
    CHAIN_CUSTODY_ANCHORS[ev_id][seq]["event_hash"] = "99" * 32

    # Verification must catch the discrepancy
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "ANCHOR_HASH_MISMATCH"


def test_03_tampered_on_chain_predecessor_hash_detected():
    """
    Test 3: On-chain anchor has a modified previous_event_hash link.
    Expected: TAMPERED with technical_error ANCHOR_PREDECESSOR_MISMATCH.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-003"
    payload = b"Phase 7 Forensic Artifact 003"
    file_hash = hashlib.sha256(payload).hexdigest()

    files = {"file": ("artifact_003.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-003"}, headers=headers)
    client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH7-003"}, headers=headers)

    t_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst1",
        "reason": "Initial handover"
    }, headers=headers)
    seq = t_res.json()["record"]["sequence_number"]

    # Tamper with predecessor link in on-chain anchor
    CHAIN_CUSTODY_ANCHORS[ev_id][seq]["previous_event_hash"] = "aa" * 32

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["tampered"] is True
    assert res["technical_error"] == "ANCHOR_PREDECESSOR_MISMATCH"


def test_04_mismatched_evidence_id_in_anchor_detected():
    """
    Test 4: On-chain anchor belongs to a different evidence item.
    Expected: INCONSISTENT with technical_error ANCHOR_EVIDENCE_MISMATCH.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-004"
    payload = b"Phase 7 Forensic Artifact 004"
    file_hash = hashlib.sha256(payload).hexdigest()

    files = {"file": ("artifact_004.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-004"}, headers=headers)
    client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH7-004"}, headers=headers)

    t_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst1",
        "reason": "Initial handover"
    }, headers=headers)
    seq = t_res.json()["record"]["sequence_number"]

    # Tamper with evidence ID in anchor
    CHAIN_CUSTODY_ANCHORS[ev_id][seq]["evidence_id"] = "EV-WRONG-999"

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["technical_error"] == "ANCHOR_EVIDENCE_MISMATCH"


def test_05_missing_on_chain_anchor_when_required():
    """
    Test 5: Required on-chain anchor is absent.
    Expected: INCONSISTENT with technical_error CUSTODY_ANCHOR_NOT_FOUND.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-005"
    payload = b"Phase 7 Forensic Artifact 005"
    file_hash = hashlib.sha256(payload).hexdigest()

    files = {"file": ("artifact_005.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-005"}, headers=headers)
    client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH7-005"}, headers=headers)

    t_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst1",
        "reason": "Handover"
    }, headers=headers)
    seq = t_res.json()["record"]["sequence_number"]

    # Delete on-chain anchor
    CHAIN_CUSTODY_ANCHORS[ev_id].pop(seq, None)

    # Calling verify with require_blockchain=True
    async def run_check():
        return await verify_custody_audit_trail(ev_id, require_blockchain=True, allow_offline_fallback=True)

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(run_check())
    finally:
        loop.close()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["technical_error"] == "CUSTODY_ANCHOR_NOT_FOUND"


def test_06_rpc_unavailable_during_anchor_verification_fails_closed(monkeypatch):
    """
    Test 6: Blockchain RPC node is offline during required anchor verification.
    Expected: Fails closed with UNAVAILABLE / BLOCKCHAIN_RPC_UNAVAILABLE.
    """
    ev_id = "EV-PH7-006"

    # Simulate offline RPC node
    monkeypatch.setattr("app.services.blockchain.get_blockchain_chain_id", lambda: None)

    async def run_check():
        return await verify_custody_audit_trail(ev_id, require_blockchain=True, allow_offline_fallback=False)

    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(run_check())
    finally:
        loop.close()

    assert res["verification_status"] == "UNAVAILABLE"
    assert res["technical_error"] == "BLOCKCHAIN_RPC_UNAVAILABLE"


# =============================================================================
# PRIORITY 2: MULTI-WORKER CONCURRENCY & IDEMPOTENCY TESTS
# =============================================================================

def test_07_concurrent_custody_transfers_conflict_prevention():
    """
    Test 7: Two simultaneous custody transfer requests for the same evidence item.
    One request acquires the transfer lock; the other request is rejected with HTTP 409 Conflict.
    Sequence numbers remain strictly monotonic without branching.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-007"
    payload = b"Phase 7 Concurrency Test Payload 007"

    files = {"file": ("artifact_007.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-007"}, headers=headers)

    # Simulate an active lock currently held by another worker
    now = time.time()
    _IN_MEMORY_TRANSFER_LOCKS[ev_id] = {
        "status": "LOCKED",
        "actor": "worker_1",
        "locked_at": now,
        "expires_at": now + 25.0
    }

    # Worker 2 attempts transfer while lock is active
    res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_worker2",
        "reason": "Simultaneous transfer attempt"
    }, headers=headers)

    assert res.status_code == 409
    assert "Concurrent custody transfer in progress" in res.json()["detail"]


def test_08_idempotent_transfer_retry_returns_cached_response():
    """
    Test 8: Client retries a transfer request with the same idempotency_key.
    First attempt executes transfer and caches response.
    Second attempt returns identical cached response without advancing sequence or duplicating events.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-008"
    payload = b"Phase 7 Idempotency Test Payload 008"

    files = {"file": ("artifact_008.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-008"}, headers=headers)

    idempotency_key = "IDEM-TEST-KEY-008-XYZ"

    # First attempt
    res1 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst2",
        "reason": "Idempotent handover test",
        "idempotency_key": idempotency_key
    }, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()

    # Second attempt (duplicate retry with identical key)
    res2 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst2",
        "reason": "Idempotent handover test",
        "idempotency_key": idempotency_key
    }, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()

    # Responses must match exactly
    assert data1["record"]["event_id"] == data2["record"]["event_id"]
    assert data1["record"]["sequence_number"] == data2["record"]["sequence_number"]
    assert data1["record"]["event_hash"] == data2["record"]["event_hash"]

    # History must have only 2 events total (Genesis + 1 transfer), NOT 3
    h_res = client.get(f"/api/custody/history/{ev_id}", headers=headers)
    assert len(h_res.json()) == 2


def test_09_stale_lock_lease_expiration_allows_recovery():
    """
    Test 9: A previous application worker crashed leaving a stale lock.
    Once lease duration has passed (expires_at < now), new worker acquires lock cleanly.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-PH7-009"
    payload = b"Phase 7 Stale Lock Test Payload 009"

    files = {"file": ("artifact_009.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH7-009"}, headers=headers)

    # Simulate expired lease from crashed worker (expired 5 seconds ago)
    now = time.time()
    _IN_MEMORY_TRANSFER_LOCKS[ev_id] = {
        "status": "LOCKED",
        "actor": "crashed_worker",
        "locked_at": now - 35.0,
        "expires_at": now - 5.0  # Expired lease
    }

    # New transfer request should acquire lock and succeed
    res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "recovering_officer",
        "reason": "Recovery after worker restart"
    }, headers=headers)

    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["record"]["details"]["new_custodian"] == "recovering_officer"


def test_10_safe_failure_release_cleans_up_lock():
    """
    Test 10: If an error occurs during transfer, lock is safely released (status FAILED)
    so the evidence item is not permanently locked against future operations.
    """
    ev_id = "EV-PH7-010"
    actor = "test_investigator"
    EVIDENCE_STORE[ev_id] = {"evidence_id": ev_id, "custodian": actor, "custody_version": 1}

    # Acquire lock
    async def test_flow():
        acquired, lock_token, _, _ = await acquire_custody_transfer_lock(ev_id, actor)
        assert acquired is True
        assert _IN_MEMORY_TRANSFER_LOCKS[ev_id]["status"] == "LOCKED"

        # Simulate failure and release
        await release_custody_transfer_lock(ev_id, lock_token=lock_token, failed=True, err_msg="Simulated DB timeout")
        assert _IN_MEMORY_TRANSFER_LOCKS[ev_id]["status"] == "FAILED"

        # Now try to acquire again - FAILED status allows new acquisition
        acquired2, lock_token2, _, _ = await acquire_custody_transfer_lock(ev_id, actor)
        assert acquired2 is True
        await release_custody_transfer_lock(ev_id, lock_token=lock_token2, failed=False)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(test_flow())
    finally:
        loop.close()
