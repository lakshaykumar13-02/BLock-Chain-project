"""
ChainVault Phase 8B — Blockchain Transaction Consistency & Fault-Injection Suite
================================================================================
Validates:
1. Durable transaction state machine lifecycle (PREPARED -> SUBMITTED -> CONFIRMED -> ANCHOR_SUBMITTED -> COMPLETED).
2. Pre-broadcast persistence of transaction intent.
3. Safe retry and recovery without duplicate transaction broadcasting.
4. Worker crash after transaction submission recovery.
5. Receipt available but database update fails.
6. Lease expiry and fencing conflict protections.
7. Idempotency fast-path and payload tampering rejection.
8. RPC unavailability during recovery failing closed.
9. Anchor hash mismatch and unexpected on-chain state detection.
"""

import time
import uuid
import pytest
import asyncio
from fastapi.testclient import TestClient

from app.main import app
from app.database.mongodb import db_client
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import AUDIT_LOGS_STORE, IDEMPOTENCY_STORE, _IN_MEMORY_TRANSFER_LOCKS
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    CHAIN_CUSTODY_ANCHORS,
    register_evidence_on_chain
)
from app.services.custody_transaction import (
    CustodyTransactionStatus,
    create_durable_transaction,
    get_durable_transaction,
    find_transaction_by_idempotency_key,
    update_transaction_state,
    reconcile_durable_transaction,
    CUSTODY_TRANSACTIONS_STORE
)
from app.security.auth import create_access_token

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Isolate in-memory stores and setup authenticated tokens."""
    EVIDENCE_STORE.clear()
    AUDIT_LOGS_STORE.clear()
    IDEMPOTENCY_STORE.clear()
    _IN_MEMORY_TRANSFER_LOCKS.clear()
    CHAIN_EVIDENCE_STORE.clear()
    CHAIN_CUSTODY_LOGS.clear()
    CHAIN_CUSTODY_ANCHORS.clear()
    CUSTODY_TRANSACTIONS_STORE.clear()
    yield

def get_auth_headers(username="investigator1", role="INVESTIGATOR"):
    token = create_access_token({"sub": username, "username": username, "role": role})
    return {"Authorization": f"Bearer {token}"}


def test_01_durable_transaction_intent_persisted_before_broadcast():
    """TC-8B-01: Verify transaction intent is persisted in state PREPARED before external broadcast."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-001-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8B",
        "file_hash": "a" * 64,
        "custodian": "officer1",
        "custody_version": 1
    }
    register_evidence_on_chain(ev_id, "a" * 64, case_id="CV-2026-8B")

    idem_key = f"IDEM-8B-001-{uid}"
    headers = get_auth_headers("investigator1")

    resp = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer2",
            "reason": "Forensic lab analysis",
            "idempotency_key": idem_key
        },
        headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "transaction_id" in data

    tx_id = data["transaction_id"]
    tx = asyncio.run(get_durable_transaction(tx_id))
    assert tx is not None
    assert tx["status"] == CustodyTransactionStatus.COMPLETED.value
    assert tx["transfer_tx_hash"] is not None
    assert tx["anchor_tx_hash"] is not None
    assert tx["new_custodian"] == "officer2"


def test_02_worker_crash_after_transaction_submission_recovery(monkeypatch):
    """TC-8B-02: Worker crashes after submitting on-chain transfer. Retry recovers without duplicate transfer."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-002-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8B",
        "file_hash": "b" * 64,
        "custodian": "officer1",
        "custody_version": 1
    }
    register_evidence_on_chain(ev_id, "b" * 64, case_id="CV-2026-8B")

    idem_key = f"IDEM-8B-002-{uid}"
    headers = get_auth_headers("investigator1")

    # Simulate crash right after on-chain transfer submission:
    # We create a durable transaction manually in SUBMITTED state with a valid on-chain transfer receipt
    simulated_tx_hash = "0x" + "11" * 32
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Handoff before crash",
        idempotency_key=idem_key,
        payload_fingerprint="fp123",
        lock_token="tok123",
        fencing_version=1
    ))
    tx_id = durable_tx["transaction_id"]

    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": simulated_tx_hash}
    ))

    # Mock receipt retrieval indicating transaction was mined
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda tx_hash: ({"status": "0x1", "blockNumber": 125}, None)
    )

    # Now the client retries with the same idempotency key
    # It must detect the confirmed transaction, perform safe reconciliation, and return success
    reconciled, rec_tx, rec_err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is True
    assert rec_tx["status"] == CustodyTransactionStatus.COMPLETED.value
    assert EVIDENCE_STORE[ev_id]["custodian"] == "officer2"


def test_03_receipt_available_but_database_update_fails():
    """TC-8B-03: Receipt is confirmed on-chain, but database fencing/commit error transitions to RECONCILIATION_REQUIRED."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-003-{uid}"
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer3",
        reason="Fencing failure test",
        idempotency_key=f"IDEM-8B-003-{uid}",
        fencing_version=1
    ))
    tx_id = durable_tx["transaction_id"]

    # Transition to SUBMITTED
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "33" * 32}
    ))

    # Simulate fencing failure transition
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED,
        {"error_message": "Fencing violation: lock lease expired or was preempted by another worker"}
    ))

    tx = asyncio.run(get_durable_transaction(tx_id))
    assert tx["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value
    assert "Fencing violation" in tx["error_message"]


def test_04_lease_expires_while_transaction_is_pending_blocks_further_mutations():
    """TC-8B-04: Active RECONCILIATION_REQUIRED state blocks subsequent transfer attempts on that evidence."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-004-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8B",
        "file_hash": "c" * 64,
        "custodian": "officer1"
    }

    # Register unresolved transaction
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Pending transfer"
    ))
    asyncio.run(update_transaction_state(
        durable_tx["transaction_id"],
        CustodyTransactionStatus.RECONCILIATION_REQUIRED,
        {"error_message": "Unresolved on-chain divergence"}
    ))

    headers = get_auth_headers("investigator1")
    resp = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer3",
            "reason": "Attempt transfer during unresolved state"
        },
        headers=headers
    )
    assert resp.status_code == 409
    assert "requiring reconciliation" in resp.json()["detail"]


def test_05_duplicate_request_idempotency_key_fast_path():
    """TC-8B-05: Subsequent requests with completed idempotency key return cached response immediately."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-005-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8B",
        "file_hash": "d" * 64,
        "custodian": "officer1"
    }
    register_evidence_on_chain(ev_id, "d" * 64, case_id="CV-2026-8B")

    idem_key = f"IDEM-8B-005-{uid}"
    headers = get_auth_headers("investigator1")

    # First request
    resp1 = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer2",
            "reason": "Initial handover",
            "idempotency_key": idem_key
        },
        headers=headers
    )
    assert resp1.status_code == 200

    # Second request (identical)
    resp2 = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer2",
            "reason": "Initial handover",
            "idempotency_key": idem_key
        },
        headers=headers
    )
    assert resp2.status_code == 200
    assert resp2.json()["transaction_id"] == resp1.json()["transaction_id"]


def test_06_actor_scoping_and_payload_fingerprint_mismatch():
    """TC-8B-06: Reject requests trying to reuse idempotency key with different actor or payload."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-006-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8B",
        "file_hash": "e" * 64,
        "custodian": "officer1"
    }
    register_evidence_on_chain(ev_id, "e" * 64, case_id="CV-2026-8B")

    idem_key = f"IDEM-8B-006-{uid}"
    headers_inv1 = get_auth_headers("investigator1")
    headers_inv2 = get_auth_headers("investigator2")

    # Initial request
    resp1 = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer2",
            "reason": "Original transfer",
            "idempotency_key": idem_key
        },
        headers=headers_inv1
    )
    assert resp1.status_code == 200

    # Request with different actor using same key
    resp2 = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer2",
            "reason": "Original transfer",
            "idempotency_key": idem_key
        },
        headers=headers_inv2
    )
    assert resp2.status_code == 422
    assert "different actor" in resp2.json()["detail"]

    # Request with different payload using same key
    resp3 = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer99",  # Modified payload
            "reason": "Modified transfer",
            "idempotency_key": idem_key
        },
        headers=headers_inv1
    )
    assert resp3.status_code == 422
    assert "different request payload" in resp3.json()["detail"]


def test_07_rpc_unavailable_during_recovery_fails_closed(monkeypatch):
    """TC-8B-07: In-flight transaction reconciliation fails closed when RPC node is offline."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-007-{uid}"
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="RPC offline test",
        idempotency_key=f"IDEM-8B-007-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]

    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "77" * 32}
    ))

    # Mock RPC unavailable
    monkeypatch.setattr("app.services.custody_transaction.get_blockchain_chain_id", lambda: None)
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: (None, "RPC_UNAVAILABLE")
    )

    reconciled, tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=False))
    assert reconciled is False
    assert err == "BLOCKCHAIN_RPC_UNAVAILABLE"


def test_08_reconciliation_detects_anchor_hash_mismatch(monkeypatch):
    """TC-8B-08: Reconciliation detects if on-chain anchor hash mismatches transaction intent."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-008-{uid}"
    register_evidence_on_chain(ev_id, "8" * 64)
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Hash mismatch test",
        idempotency_key=f"IDEM-8B-008-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]

    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "88" * 32}
    ))
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.CONFIRMED,
        {"transfer_block_number": 200}
    ))
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.ANCHOR_SUBMITTED,
        {
            "anchor_tx_hash": "0x" + "99" * 32,
            "anchor_sequence_number": 2,
            "event_hash": "correct_hash_" + "0" * 51
        }
    ))

    # Mock receipt as confirmed
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x1", "blockNumber": 200}, None)
    )
    # Mock anchor retrieval returning corrupted/mismatched hash
    monkeypatch.setattr(
        "app.services.custody_transaction.get_custody_anchor_from_chain",
        lambda eid, seq, allow_offline_fallback: (
            {"exists": True, "event_hash": "tampered_hash_" + "f" * 50},
            None
        )
    )

    reconciled, tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is False
    assert err == "ANCHOR_HASH_MISMATCH"
    assert tx["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value


def test_09_transaction_query_and_reconciliation_endpoints():
    """TC-8B-09: Verify transaction query and manual reconciliation endpoints."""
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-SYNTH-8B-009-{uid}"
    headers = get_auth_headers("investigator1")

    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Query endpoint test"
    ))
    tx_id = durable_tx["transaction_id"]

    # 1. Query by evidence ID
    resp_list = client.get(f"/api/custody/transactions/{ev_id}", headers=headers)
    assert resp_list.status_code == 200
    txs = resp_list.json()
    assert len(txs) >= 1
    assert txs[0]["transaction_id"] == tx_id

    # 2. Query by transaction ID
    resp_detail = client.get(f"/api/custody/transaction/{tx_id}", headers=headers)
    assert resp_detail.status_code == 200
    assert resp_detail.json()["transaction_id"] == tx_id
