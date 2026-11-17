"""
ChainVault Phase 7.1 — Implementation Audit & Real Local-EVM Validation Suite
=============================================================================
This test suite covers deterministic synthetic tests for:
Task 2: Audit Lease Locking (atomic operations, lock token verification,
        fencing tokens, lease renewals, crash recovery, and expiry preemption).
Task 3: Audit Idempotency (actor scoping, payload fingerprinting, in-progress
        conflict rejection, durable MongoDB authoritative state, worker restarts).
Task 5: End-to-End Cryptographic Custody Integrity (canonical generation,
        hash persistence, on-chain anchor retrieval, predecessor chaining,
        tampered event detection, and fail-closed RPC resilience).
"""

import io
import os
import re
import time
import asyncio
import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.mongodb import db_client
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import (
    AUDIT_LOGS_STORE,
    _IN_MEMORY_TRANSFER_LOCKS,
    IDEMPOTENCY_STORE,
    acquire_custody_transfer_lock,
    renew_custody_transfer_lock,
    release_custody_transfer_lock,
    calculate_transfer_payload_fingerprint
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
    get_stored_custody_events,
    persist_custody_event
)

client = TestClient(app)

SYNTHETIC_PREFIX = "EV-AUDIT71-"


def get_auth_token(username="investigator1"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200, f"Authentication failed for {username}: {res.text}"
    return res.json()["access_token"]


def ingest_synthetic_evidence(evidence_id: str, case_id: str = "CV-2026-T71", content: bytes = b"Synthetic Payload", register_chain: bool = False):
    """Helper to cleanly ingest synthetic evidence and optionally register on blockchain."""
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": (f"{evidence_id}.bin", io.BytesIO(content), "application/octet-stream")}
    res = client.post("/api/evidence/upload", files=files, data={"evidence_id": evidence_id, "case_id": case_id}, headers=headers)
    assert res.status_code == 201, f"Ingestion failed: {res.text}"

    if register_chain:
        file_hash = hashlib.sha256(content).hexdigest()
        reg_res = client.post("/api/blockchain/register", json={"evidence_id": evidence_id, "hash": file_hash, "case_id": case_id}, headers=headers)
        assert reg_res.status_code == 200, f"Blockchain registration failed: {reg_res.text}"

    return res.json()


@pytest.fixture(scope="module", autouse=True)
def setup_db_connection():
    """Ensure MongoDB connection is active for Phase 7.1 audit suite."""
    asyncio.run(db_client.connect())


@pytest.fixture(autouse=True)
def cleanup_synthetic_audit_state():
    """Ensure all synthetic test records are cleaned up before and after each test."""
    def _cleanup():
        keys_ev = [k for k in list(EVIDENCE_STORE.keys()) if k.startswith(SYNTHETIC_PREFIX)]
        for k in keys_ev:
            rec = EVIDENCE_STORE.pop(k, None)
            if rec and rec.get("file_path") and os.path.exists(rec["file_path"]):
                try:
                    os.remove(rec["file_path"])
                except OSError:
                    pass
        for k in list(AUDIT_LOGS_STORE.keys()):
            if k.startswith(SYNTHETIC_PREFIX):
                AUDIT_LOGS_STORE.pop(k, None)
        for k in list(CHAIN_EVIDENCE_STORE.keys()):
            if k.startswith(SYNTHETIC_PREFIX):
                CHAIN_EVIDENCE_STORE.pop(k, None)
        for k in list(CHAIN_CUSTODY_LOGS.keys()):
            if k.startswith(SYNTHETIC_PREFIX):
                CHAIN_CUSTODY_LOGS.pop(k, None)
        for k in list(CHAIN_CUSTODY_ANCHORS.keys()):
            if k.startswith(SYNTHETIC_PREFIX):
                CHAIN_CUSTODY_ANCHORS.pop(k, None)
        for k in list(_IN_MEMORY_TRANSFER_LOCKS.keys()):
            if k.startswith(SYNTHETIC_PREFIX):
                _IN_MEMORY_TRANSFER_LOCKS.pop(k, None)
        # Clear idempotency keys used in audit tests
        for k in list(IDEMPOTENCY_STORE.keys()):
            if k.startswith("IDEM-AUDIT71-"):
                IDEMPOTENCY_STORE.pop(k, None)

        # Clean MongoDB test records if connected
        if db_client.is_connected() and db_client.db is not None:
            pat = re.compile(f"^{SYNTHETIC_PREFIX}")
            pat_idem = re.compile(r"^IDEM-AUDIT71-")
            async def _purge():
                try:
                    await db_client.evidence.delete_many({"evidence_id": pat})
                    await db_client.audit_logs.delete_many({"evidence_id": pat})
                    await db_client.db["idempotency_records"].delete_many({"idempotency_key": pat_idem})
                except Exception:
                    pass
            try:
                asyncio.run(_purge())
            except Exception:
                pass

    _cleanup()
    yield
    _cleanup()


# =============================================================================
# TASK 2: LEASE LOCKING & FENCING TOKEN TESTS
# =============================================================================

def test_t2_01_atomic_exclusive_lock_acquisition():
    """
    Task 2.1: Lock acquisition is atomic and exclusive.
    Only one valid owner can acquire the lock for a given evidence ID.
    Second concurrent worker receives HTTP 409 Conflict.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}001"
    ingest_synthetic_evidence(ev_id)

    # Worker 1 holds active lock in memory and MongoDB
    now = time.time()
    lock_doc = {
        "status": "LOCKED",
        "actor": "worker_node_alpha",
        "lock_token": "token-worker-alpha-12345",
        "locked_at": now,
        "expires_at": now + 30.0,
        "fencing_version": 1
    }
    _IN_MEMORY_TRANSFER_LOCKS[ev_id] = dict(lock_doc)
    if db_client.is_connected():
        async def _set_lock():
            await db_client.evidence.update_one(
                {"evidence_id": ev_id},
                {"$set": {"transfer_lock": lock_doc}}
            )
        asyncio.run(_set_lock())

    # Worker 2 attempts transfer while lock is active -> 409 Conflict
    res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_beta",
        "reason": "Simultaneous transfer conflict check"
    }, headers=headers)

    assert res.status_code == 409
    assert "Concurrent custody transfer in progress" in res.json()["detail"]


def test_t2_02_lock_release_verifies_ownership():
    """
    Task 2.2: Lock release checks ownership and cannot release another worker's lock.
    Worker A cannot release Worker B's active lock with a mismatched lock_token.
    """
    ev_id = f"{SYNTHETIC_PREFIX}002"
    ingest_synthetic_evidence(ev_id)
    actor_a = "worker_alpha"

    async def flow():
        # Worker A acquires lock
        acquired_a, token_a, _, ver_a = await acquire_custody_transfer_lock(ev_id, actor_a)
        assert acquired_a is True
        assert token_a is not None

        # Worker B attempts to release Worker A's lock using a bogus token
        released_by_b = await release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token="bogus-foreign-token-from-worker-b",
            new_custodian="officer_tamper",
            failed=False
        )
        assert released_by_b is False, "Release must fail when lock_token does not match owner"

        # Worker A's lock must still remain active
        if ev_id in _IN_MEMORY_TRANSFER_LOCKS:
            assert _IN_MEMORY_TRANSFER_LOCKS[ev_id]["status"] == "LOCKED"
            assert _IN_MEMORY_TRANSFER_LOCKS[ev_id]["lock_token"] == token_a

        # Worker A cleanly releases their own lock
        released_by_a = await release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=token_a,
            failed=False
        )
        assert released_by_a is True

    asyncio.run(flow())


def test_t2_03_fencing_token_prevents_stale_commit():
    """
    Task 2.3: Long-running operations renew leases safely or use fencing tokens
    to prevent stale workers from committing.
    Simulate: Worker A holds lock, experiences long RPC timeout, lease expires.
    Worker B acquires lock, updates state and advances custody version.
    Worker A attempts commit with old expected_version -> Fails closed with False.
    """
    ev_id = f"{SYNTHETIC_PREFIX}003"
    ingest_synthetic_evidence(ev_id)

    async def flow():
        # Worker A acquires lock with expected_version = 1
        acq_a, token_a, _, ver_a = await acquire_custody_transfer_lock(ev_id, "worker_alpha")
        assert acq_a is True

        # Simulate Worker A stalling (RPC timeout).
        # Lease expires and Worker B preempts lock and commits a transfer:
        _IN_MEMORY_TRANSFER_LOCKS.pop(ev_id, None)
        if db_client.is_connected() and db_client.db is not None:
            await db_client.evidence.update_one(
                {"evidence_id": ev_id},
                {"$set": {"custody_version": 2, "custodian": "officer_beta"}, "$unset": {"transfer_lock": ""}}
            )
        EVIDENCE_STORE[ev_id]["custody_version"] = 2
        EVIDENCE_STORE[ev_id]["custodian"] = "officer_beta"

        # Now Worker A wakes up and attempts to commit with stale token_a and stale ver_a
        rel_a = await release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=token_a,
            new_custodian="officer_alpha_stale",
            expected_version=ver_a,
            failed=False
        )
        # Release must fail: version in db/memory has advanced past ver_a
        assert rel_a is False
        # Custodian must remain officer_beta, NOT overwritten by stale worker
        assert EVIDENCE_STORE[ev_id]["custodian"] == "officer_beta"

    asyncio.run(flow())


def test_t2_04_lease_renewal_for_long_running_operation():
    """
    Task 2.4: Long-running operations renew leases safely.
    Valid worker extends expiration before lease ends.
    """
    ev_id = f"{SYNTHETIC_PREFIX}004"
    ingest_synthetic_evidence(ev_id)
    actor = "worker_long_running"

    async def flow():
        acquired, lock_token, _, _ = await acquire_custody_transfer_lock(ev_id, actor, lease_seconds=5.0)
        assert acquired is True

        # Renew lease for additional 30 seconds
        renewed = await renew_custody_transfer_lock(ev_id, lock_token=lock_token, additional_seconds=30.0)
        assert renewed is True

        # Attempt to renew with bogus token fails
        renew_bogus = await renew_custody_transfer_lock(ev_id, lock_token="wrong_token", additional_seconds=30.0)
        assert renew_bogus is False

        # Clean up
        await release_custody_transfer_lock(ev_id, lock_token=lock_token, failed=False)

    asyncio.run(flow())


def test_t2_05_crashed_worker_lease_expiration_and_recovery():
    """
    Task 2.5: Worker crashes and restart recovery are handled explicitly.
    A stale lock with expires_at in the past does not block subsequent operations.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}005"
    ingest_synthetic_evidence(ev_id)

    # Simulate crashed worker leaving lock that expired 10 seconds ago
    now = time.time()
    crashed_lock = {
        "status": "LOCKED",
        "actor": "crashed_worker_node_9",
        "lock_token": "token-crashed-node-9",
        "locked_at": now - 40.0,
        "expires_at": now - 10.0,  # Expired
        "fencing_version": 1
    }
    _IN_MEMORY_TRANSFER_LOCKS[ev_id] = dict(crashed_lock)
    if db_client.is_connected():
        async def _set_crashed():
            await db_client.evidence.update_one(
                {"evidence_id": ev_id},
                {"$set": {"transfer_lock": crashed_lock}}
            )
        asyncio.run(_set_crashed())

    # Recovering worker performs transfer -> Succeeds
    res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "recovery_officer_1",
        "reason": "Transfer after worker crash"
    }, headers=headers)

    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["record"]["details"]["new_custodian"] == "recovery_officer_1"


# =============================================================================
# TASK 3: IDEMPOTENCY AUDIT & RETRY BEHAVIOR TESTS
# =============================================================================

def test_t3_01_idempotency_actor_scoping_rejection():
    """
    Task 3.1: Verify idempotency keys are scoped correctly to the authenticated actor.
    Key reuse by a different actor is rejected with HTTP 422 Unprocessable Entity.
    """
    token1 = get_auth_token("investigator1")
    token2 = get_auth_token("admin")
    ev_id = f"{SYNTHETIC_PREFIX}006"
    ingest_synthetic_evidence(ev_id)

    idem_key = "IDEM-AUDIT71-KEY-006"

    # User 1 performs transfer with idempotency key
    res1 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_alice",
        "reason": "Handover by investigator1",
        "idempotency_key": idem_key
    }, headers={"Authorization": f"Bearer {token1}"})
    assert res1.status_code == 200

    # User 2 (admin) attempts to use the SAME idempotency key
    res2 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_alice",
        "reason": "Handover by investigator1",
        "idempotency_key": idem_key
    }, headers={"Authorization": f"Bearer {token2}"})

    assert res2.status_code == 422
    assert "previously used by a different actor" in res2.json()["detail"]


def test_t3_02_idempotency_payload_mismatch_rejection():
    """
    Task 3.2: Key reuse with a different payload is rejected with HTTP 422 Unprocessable Entity.
    Same actor attempts to reuse key with modified custodian or reason.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}007"
    ingest_synthetic_evidence(ev_id)

    idem_key = "IDEM-AUDIT71-KEY-007"

    # Original request
    res1 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "analyst_carol",
        "reason": "Original transfer reason",
        "idempotency_key": idem_key
    }, headers=headers)
    assert res1.status_code == 200

    # Tampered request reusing same key with different new_custodian
    res2 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "different_custodian_dave",
        "reason": "Original transfer reason",
        "idempotency_key": idem_key
    }, headers=headers)

    assert res2.status_code == 422
    assert "different request payload" in res2.json()["detail"]


def test_t3_03_idempotency_in_progress_duplicate_rejection():
    """
    Task 3.3: Duplicate request arriving while first request is IN_PROGRESS is rejected with HTTP 409 Conflict.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}008"
    ingest_synthetic_evidence(ev_id)
    idem_key = "IDEM-AUDIT71-KEY-008"

    payload_fp = calculate_transfer_payload_fingerprint(ev_id, "officer_in_progress", "Test in progress")

    in_progress_doc = {
        "idempotency_key": idem_key,
        "actor_id": "investigator1",
        "evidence_id": ev_id,
        "payload_fingerprint": payload_fp,
        "status": "IN_PROGRESS",
        "created_at": time.time()
    }
    IDEMPOTENCY_STORE[idem_key] = dict(in_progress_doc)
    if db_client.is_connected():
        async def _set_in_progress():
            await db_client.db["idempotency_records"].update_one(
                {"idempotency_key": idem_key},
                {"$set": in_progress_doc},
                upsert=True
            )
        asyncio.run(_set_in_progress())

    # Concurrent request with same key
    res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_in_progress",
        "reason": "Test in progress",
        "idempotency_key": idem_key
    }, headers=headers)

    assert res.status_code == 409
    assert "currently in progress" in res.json()["detail"]


def test_t3_04_idempotency_authoritative_mongodb_across_restart():
    """
    Task 3.4: Durable state in MongoDB must be authoritative.
    An in-memory cache must not be required for correctness.
    Simulate worker restart by completely clearing in-memory IDEMPOTENCY_STORE.
    Authoritative state is loaded and duplicate transfer is prevented.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}009"
    ingest_synthetic_evidence(ev_id)

    idem_key = "IDEM-AUDIT71-KEY-009"

    # Step 1: Execute initial transfer
    res1 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_restart_1",
        "reason": "Transfer before simulated restart",
        "idempotency_key": idem_key
    }, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()

    # Step 2: Simulate Application Worker Restart
    # Wipe the in-memory cache completely
    IDEMPOTENCY_STORE.clear()
    assert idem_key not in IDEMPOTENCY_STORE

    # Step 3: Resend identical request on new application worker
    # Must retrieve cached response from authoritative MongoDB storage without creating duplicate event
    res2 = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_restart_1",
        "reason": "Transfer before simulated restart",
        "idempotency_key": idem_key
    }, headers=headers)

    assert res2.status_code == 200
    data2 = res2.json()
    assert data1["record"]["event_id"] == data2["record"]["event_id"]
    assert data1["record"]["sequence_number"] == data2["record"]["sequence_number"]


# =============================================================================
# TASK 5: END-TO-END CRYPTOGRAPHIC INTEGRITY TESTS
# =============================================================================

def test_t5_01_e2e_custody_anchor_generation_and_verification():
    """
    Task 5.1: Complete flow:
    1. Generate a canonical custody event.
    2. Compute and persist its hash.
    3. Record the corresponding anchor on the blockchain.
    4. Retrieve the anchor independently from the contract.
    5. Recompute the event hash and verify its predecessor chain.
    Verify that verification returns VERIFIED.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}010"
    ingest_synthetic_evidence(ev_id, register_chain=True)

    # Step 3: Transfer custody with on-chain anchor
    trans_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "lead_detective_501",
        "reason": "Custody handover for laboratory forensics"
    }, headers=headers)
    assert trans_res.status_code == 200
    transfer_record = trans_res.json()["record"]
    seq = transfer_record["sequence_number"]
    assert seq == 3

    # Step 4: Retrieve anchor independently
    anchor, err = get_custody_anchor_from_chain(ev_id, seq)
    assert err is None
    assert anchor is not None
    assert anchor["event_hash"] == transfer_record["event_hash"]
    assert anchor["previous_event_hash"] == transfer_record["previous_event_hash"]

    # Step 5: Verify complete custody trail via audit verification endpoint
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    ver_res = v_res.json()
    assert ver_res["verification_status"] == "VERIFIED"
    assert ver_res["verified"] is True
    assert ver_res["chain_intact"] is True
    assert ver_res["blockchain_reconciled"] is True


def test_t5_02_e2e_tampered_event_content_detected():
    """
    Task 5.2: Modify synthetic event content and confirm verification fails with TAMPERED.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}011"
    ingest_synthetic_evidence(ev_id, register_chain=True)

    client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_502",
        "reason": "Legitimate handover"
    }, headers=headers)

    # Tamper with event 2 in the store and in MongoDB
    if ev_id in AUDIT_LOGS_STORE:
        AUDIT_LOGS_STORE[ev_id][1]["details"]["reason"] = "FRAUDULENT_ALTERED_REASON"
    if db_client.is_connected():
        async def _tamper():
            await db_client.audit_logs.update_one(
                {"evidence_id": ev_id, "sequence_number": 2},
                {"$set": {"details.reason": "FRAUDULENT_ALTERED_REASON"}}
            )
        asyncio.run(_tamper())

    async def verify():
        return await verify_custody_audit_trail(ev_id, require_blockchain=True)

    ver_res = asyncio.run(verify())
    assert ver_res["verification_status"] == "TAMPERED"
    assert ver_res["tampered"] is True
    assert ver_res["verified"] is False
    assert ver_res["technical_error"] == "EVENT_HASH_MISMATCH"


def test_t5_03_e2e_tampered_predecessor_link_detected():
    """
    Task 5.3: Modify synthetic event predecessor link and confirm verification fails with TAMPERED.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}012"
    ingest_synthetic_evidence(ev_id, register_chain=True)

    client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_503",
        "reason": "Legitimate handover"
    }, headers=headers)

    # Tamper with predecessor link in sequence 2 in memory and MongoDB
    new_prev_hash = "deadbeef" * 8
    new_ev_hash = "beefdead" * 8
    if ev_id in AUDIT_LOGS_STORE:
        AUDIT_LOGS_STORE[ev_id][1]["previous_event_hash"] = new_prev_hash
        tampered_event = AUDIT_LOGS_STORE[ev_id][1]
        tampered_event["event_hash"] = calculate_canonical_event_hash(tampered_event)
        new_ev_hash = tampered_event["event_hash"]

    if db_client.is_connected():
        async def _tamper_prev():
            await db_client.audit_logs.update_one(
                {"evidence_id": ev_id, "sequence_number": 2},
                {"$set": {"previous_event_hash": new_prev_hash, "event_hash": new_ev_hash}}
            )
        asyncio.run(_tamper_prev())

    async def verify():
        return await verify_custody_audit_trail(ev_id, require_blockchain=True)

    ver_res = asyncio.run(verify())
    assert ver_res["verification_status"] == "TAMPERED"
    assert ver_res["tampered"] is True
    assert ver_res["verified"] is False
    assert ver_res["technical_error"] in ("BROKEN_PREDECESSOR_LINK", "ANCHOR_PREDECESSOR_MISMATCH", "ANCHOR_HASH_MISMATCH")


def test_t5_04_e2e_rpc_failure_fails_closed(monkeypatch):
    """
    Task 5.4: Simulate RPC failure and confirm fail-closed behavior.
    Verification must return UNAVAILABLE (never silent VERIFIED).
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}013"
    ingest_synthetic_evidence(ev_id, register_chain=True)

    t_res = client.post("/api/custody/transfer", json={
        "evidence_id": ev_id,
        "new_custodian": "officer_504",
        "reason": "Legitimate handover before simulated RPC drop"
    }, headers=headers)
    assert t_res.status_code == 200

    # Simulate offline RPC node
    monkeypatch.setattr("app.services.blockchain.get_blockchain_chain_id", lambda: None)

    async def verify():
        return await verify_custody_audit_trail(ev_id, require_blockchain=True, allow_offline_fallback=False)

    ver_res = asyncio.run(verify())
    assert ver_res["verification_status"] == "UNAVAILABLE"
    assert ver_res["verified"] is False
    assert ver_res["technical_error"] == "BLOCKCHAIN_RPC_UNAVAILABLE"
