"""
ChainVault Phase 8C — Independent Transaction Recovery Audit Test Suite
=======================================================================
Deterministic fault-injection and recovery validation across all 10 critical failure windows:
1. RPC accepts a transaction, but the client times out before receiving its transaction hash.
2. Worker crashes after broadcast but before persisting the transaction hash.
3. Worker crashes after receipt confirmation but before updating MongoDB.
4. Lease expires while a transaction is pending and another worker takes ownership.
5. Anchor succeeds on-chain but MongoDB persistence fails.
6. RPC is unavailable or returns incomplete transaction/receipt data during recovery.
7. Duplicate requests arrive concurrently from separate workers.
8. A transaction receipt belongs to the wrong chain or contract.
9. On-chain evidence, custodian, sequence, or anchor hash differs from expected state.
10. A transaction is pending, replaced, dropped, reverted, or temporarily unavailable.
"""

import time
import uuid
import pytest
import asyncio
from fastapi.testclient import TestClient

from app.main import app
from app.database.mongodb import db_client
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import (
    AUDIT_LOGS_STORE,
    IDEMPOTENCY_STORE,
    _IN_MEMORY_TRANSFER_LOCKS,
    calculate_transfer_payload_fingerprint,
    acquire_custody_transfer_lock
)
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    CHAIN_CUSTODY_ANCHORS,
    register_evidence_on_chain,
    CONTRACT_ADDRESS,
    EXPECTED_CHAIN_ID
)
from app.services.custody_transaction import (
    CustodyTransactionStatus,
    create_durable_transaction,
    get_durable_transaction,
    update_transaction_state,
    reconcile_durable_transaction,
    CUSTODY_TRANSACTIONS_STORE
)
from app.security.auth import create_access_token

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Ensure in-memory stores are cleanly isolated for each test."""
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


# =============================================================================
# WINDOW 1 & 2: TIMEOUT OR CRASH BEFORE HASH PERSISTENCE (UNCERTAIN OUTCOME)
# =============================================================================

def test_tc8c_01_timeout_before_hash_persistence_blocks_evidence():
    """
    TC-8C-01: RPC accepts transaction but client times out before receiving hash.
    Outcome is uncertain; fail closed to RECONCILIATION_REQUIRED, never mark FAILED or COMPLETED.
    Subsequent transfers on evidence are blocked with HTTP 409.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-001-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8C",
        "file_hash": "1" * 64,
        "custodian": "officer1"
    }
    register_evidence_on_chain(ev_id, "1" * 64)

    # Intent is created in PREPARED, but worker disconnects before recording transfer_tx_hash
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Timeout before hash test",
        idempotency_key=f"IDEM-8C-001-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]

    # Reconciliation attempts recovery
    reconciled, tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is False
    assert err == "UNCERTAIN_BROADCAST_OUTCOME"
    assert tx["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value
    assert "Uncertain broadcast outcome" in tx["error_message"]

    # Subsequent transfer attempt is blocked fail-closed
    headers = get_auth_headers("investigator1")
    resp = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer3",
            "reason": "Attempt mutation during uncertain state"
        },
        headers=headers
    )
    assert resp.status_code == 409
    assert "requiring reconciliation" in resp.json()["detail"]


def test_tc8c_02_crash_after_broadcast_before_hash_persistence_requires_manual():
    """
    TC-8C-02: Worker crashes right after broadcast.
    No transaction hash persisted; reconciliation requires manual intervention rather than blind retry.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-002-{uid}"
    register_evidence_on_chain(ev_id, "2" * 64)

    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Crash before hash test",
        idempotency_key=f"IDEM-8C-002-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]

    # Must fail closed without silently assuming not broadcast
    reconciled, tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is False
    assert err == "UNCERTAIN_BROADCAST_OUTCOME"
    assert tx["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value


# =============================================================================
# WINDOW 3: CRASH AFTER CONFIRMATION BUT BEFORE MONGODB UPDATE
# =============================================================================

def test_tc8c_03_crash_after_receipt_confirmation_recovers_to_completed(monkeypatch):
    """
    TC-8C-03: On-chain transfer is mined and confirmed, but worker crashes before updating MongoDB.
    Reconciliation verifies on-chain receipt, commits new custodian, and completes transaction.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-003-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8C",
        "file_hash": "3" * 64,
        "custodian": "officer1",
        "custody_version": 1
    }
    register_evidence_on_chain(ev_id, "3" * 64)

    sim_tx_hash = "0x" + "33" * 32
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Crash after confirmation",
        idempotency_key=f"IDEM-8C-003-{uid}",
        fencing_version=1
    ))
    tx_id = durable_tx["transaction_id"]

    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": sim_tx_hash}
    ))

    # Mock receipt as confirmed
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x1", "blockNumber": 350, "to": CONTRACT_ADDRESS}, None)
    )

    reconciled, rec_tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is True
    assert err is None
    assert rec_tx["status"] == CustodyTransactionStatus.COMPLETED.value
    assert EVIDENCE_STORE[ev_id]["custodian"] == "officer2"


# =============================================================================
# WINDOW 4: LEASE EXPIRY & STALE WORKER FENCING CONFLICT
# =============================================================================

def test_tc8c_04_lease_expires_and_fencing_version_conflict_fails_closed(monkeypatch):
    """
    TC-8C-04: Lease expires while worker is executing. Another worker advances custody_version.
    Stale worker attempting reconciliation detects version conflict and enters RECONCILIATION_REQUIRED.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-004-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8C",
        "file_hash": "4" * 64,
        "custodian": "officer1",
        "custody_version": 2  # Current DB version advanced past worker's expected version 1
    }
    register_evidence_on_chain(ev_id, "4" * 64)

    sim_tx_hash = "0x" + "44" * 32
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Fencing conflict test",
        fencing_version=1  # Expected 1, but active version is 2
    ))
    tx_id = durable_tx["transaction_id"]

    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": sim_tx_hash}
    ))

    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x1", "blockNumber": 400, "to": CONTRACT_ADDRESS}, None)
    )

    # In MongoDB-connected environment, simulate DB doc having advanced version
    if db_client.is_connected():
        async def _seed_conflict():
            await db_client.evidence.update_one(
                {"evidence_id": ev_id},
                {"$set": {"custody_version": 2, "custodian": "officer99"}},
                upsert=True
            )
        asyncio.run(_seed_conflict())

    reconciled, tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is False
    assert err == "FENCING_CONFLICT"
    assert tx["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value


# =============================================================================
# WINDOW 5: ANCHOR SUCCEEDS BUT APPLICATION PERSISTENCE FAILS
# =============================================================================

def test_tc8c_05_anchor_succeeds_on_chain_recovered_independently(monkeypatch):
    """
    TC-8C-05: Custody anchor transaction succeeds on-chain, but worker interrupted before DB commit.
    Reconciliation queries getCustodyAnchor on-chain and recovers state.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-005-{uid}"
    register_evidence_on_chain(ev_id, "5" * 64)

    canonical_hash = "55" * 32
    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Anchor success recovery",
        idempotency_key=f"IDEM-8C-005-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]

    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "51" * 32}
    ))
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.CONFIRMED,
        {"transfer_block_number": 500}
    ))
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.ANCHOR_SUBMITTED,
        {
            "anchor_tx_hash": "0x" + "52" * 32,
            "anchor_sequence_number": 2,
            "event_hash": canonical_hash
        }
    ))

    # Mock receipts
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x1", "blockNumber": 501, "to": CONTRACT_ADDRESS}, None)
    )
    # Mock anchor retrieval from chain
    monkeypatch.setattr(
        "app.services.custody_transaction.get_custody_anchor_from_chain",
        lambda eid, seq, allow_offline_fallback: (
            {"exists": True, "event_hash": canonical_hash, "sequence_number": 2},
            None
        )
    )

    reconciled, tx, err = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled is True
    assert err is None
    assert tx["status"] == CustodyTransactionStatus.COMPLETED.value


# =============================================================================
# WINDOW 6: RPC UNAVAILABLE OR INCOMPLETE RECEIPT DATA
# =============================================================================

def test_tc8c_06_rpc_unavailable_and_incomplete_receipt_handling(monkeypatch):
    """
    TC-8C-06:
    A) RPC offline during recovery returns BLOCKCHAIN_RPC_UNAVAILABLE.
    B) Receipt returned with missing/None status returns INCOMPLETE_RECEIPT_DATA.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-006-{uid}"
    register_evidence_on_chain(ev_id, "6" * 64)

    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="RPC incomplete test",
        idempotency_key=f"IDEM-8C-006-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "66" * 32}
    ))

    # Scenario A: RPC offline
    monkeypatch.setattr("app.services.custody_transaction.get_blockchain_chain_id", lambda: None)
    reconciled_a, tx_a, err_a = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=False))
    assert reconciled_a is False
    assert err_a == "BLOCKCHAIN_RPC_UNAVAILABLE"

    # Scenario B: RPC online, but receipt has status=None (malformed/incomplete data)
    monkeypatch.setattr("app.services.custody_transaction.get_blockchain_chain_id", lambda: EXPECTED_CHAIN_ID)
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": None, "blockNumber": 600, "to": CONTRACT_ADDRESS}, "INCOMPLETE_RECEIPT_DATA")
    )
    reconciled_b, tx_b, err_b = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=False))
    assert reconciled_b is False
    assert err_b == "INCOMPLETE_RECEIPT_DATA"
    assert tx_b["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value


# =============================================================================
# WINDOW 7: CONCURRENT DUPLICATE REQUESTS (IN_PROGRESS LOCK)
# =============================================================================

def test_tc8c_07_concurrent_duplicate_requests_rejected_in_progress():
    """
    TC-8C-07: Duplicate request arriving while transaction is actively IN_PROGRESS is rejected with HTTP 409.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-007-{uid}"
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-2026-8C",
        "file_hash": "7" * 64,
        "custodian": "officer1"
    }
    register_evidence_on_chain(ev_id, "7" * 64)

    idem_key = f"IDEM-8C-007-{uid}"
    headers = get_auth_headers("investigator1")

    # Simulate an active in-progress transaction locked by Worker 1
    _IN_MEMORY_TRANSFER_LOCKS[ev_id] = {
        "status": "LOCKED",
        "actor": "investigator1",
        "lock_token": "active-token",
        "idempotency_key": idem_key,
        "locked_at": time.time(),
        "expires_at": time.time() + 60.0,
        "fencing_version": 1
    }
    asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Concurrent test",
        idempotency_key=idem_key
    ))
    IDEMPOTENCY_STORE[idem_key] = {
        "idempotency_key": idem_key,
        "actor_id": "investigator1",
        "evidence_id": ev_id,
        "status": "IN_PROGRESS",
        "started_at": time.time()
    }

    # Worker 2 submits request with same idempotency key concurrently
    resp = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": ev_id,
            "new_custodian": "officer2",
            "reason": "Concurrent test",
            "idempotency_key": idem_key
        },
        headers=headers
    )
    assert resp.status_code == 409
    assert "currently in progress" in resp.json()["detail"]


# =============================================================================
# WINDOW 8: RECEIPT WRONG CHAIN OR WRONG CONTRACT ADDRESS
# =============================================================================

def test_tc8c_08_receipt_wrong_contract_or_chain_id_rejected(monkeypatch):
    """
    TC-8C-08:
    A) Transaction receipt target contract address does not match CONTRACT_ADDRESS.
    B) Connected RPC Chain ID does not match EXPECTED_CHAIN_ID.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-008-{uid}"
    register_evidence_on_chain(ev_id, "8" * 64)

    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Wrong contract test",
        idempotency_key=f"IDEM-8C-008-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "88" * 32}
    ))

    # Scenario A: Receipt points to a different/foreign contract address
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x1", "blockNumber": 800, "to": "0x000000000000000000000000000000000000DEAD"}, None)
    )
    reconciled_a, tx_a, err_a = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert reconciled_a is False
    assert err_a == "CONTRACT_ADDRESS_MISMATCH"
    assert tx_a["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value

    # Scenario B: Chain ID mismatch (e.g. connected to wrong network)
    monkeypatch.setattr("app.services.custody_transaction.get_blockchain_chain_id", lambda: 1)  # Mainnet instead of local/sepolia
    reconciled_b, tx_b, err_b = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=False))
    assert reconciled_b is False
    assert err_b == "CHAIN_ID_MISMATCH"


# =============================================================================
# WINDOW 9: ON-CHAIN STATE DIVERGENCE (ANCHOR HASH / EVIDENCE MISMATCH)
# =============================================================================

def test_tc8c_09_on_chain_hash_or_missing_evidence_detected(monkeypatch):
    """
    TC-8C-09:
    A) Evidence not found on-chain returns ON_CHAIN_EVIDENCE_NOT_FOUND.
    B) On-chain anchor hash mismatch returns ANCHOR_HASH_MISMATCH.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-009-{uid}"
    # Do NOT register evidence on chain for Scenario A

    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Divergence test",
        idempotency_key=f"IDEM-8C-009-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "99" * 32}
    ))

    # Scenario A: Evidence does not exist on-chain
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x1", "blockNumber": 900, "to": CONTRACT_ADDRESS}, None)
    )
    reconciled_a, tx_a, err_a = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=False))
    assert reconciled_a is False
    assert err_a == "ON_CHAIN_EVIDENCE_NOT_FOUND"

    # Scenario B: Evidence exists on chain, but anchor hash mismatches intent
    ev_id_b = f"EV-8C-009B-{uid}"
    register_evidence_on_chain(ev_id_b, "9" * 64)
    durable_tx_b = asyncio.run(create_durable_transaction(
        evidence_id=ev_id_b,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Anchor mismatch test"
    ))
    tx_id_b = durable_tx_b["transaction_id"]
    asyncio.run(update_transaction_state(
        tx_id_b,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "92" * 32}
    ))
    asyncio.run(update_transaction_state(
        tx_id_b,
        CustodyTransactionStatus.CONFIRMED,
        {"transfer_block_number": 901}
    ))
    asyncio.run(update_transaction_state(
        tx_id_b,
        CustodyTransactionStatus.ANCHOR_SUBMITTED,
        {
            "anchor_tx_hash": "0x" + "91" * 32,
            "anchor_sequence_number": 2,
            "event_hash": "expected_canonical_hash_" + "0" * 40
        }
    ))
    monkeypatch.setattr(
        "app.services.custody_transaction.get_custody_anchor_from_chain",
        lambda eid, seq, allow_offline_fallback: (
            {"exists": True, "event_hash": "tampered_divergent_hash_" + "f" * 39},
            None
        )
    )
    reconciled_b, tx_b, err_b = asyncio.run(reconcile_durable_transaction(tx_id_b, allow_offline_fallback=True))
    assert reconciled_b is False
    assert err_b == "ANCHOR_HASH_MISMATCH"


# =============================================================================
# WINDOW 10: PENDING, DROPPED, AND REVERTED TRANSACTIONS
# =============================================================================

def test_tc8c_10_pending_dropped_and_reverted_transactions(monkeypatch):
    """
    TC-8C-10:
    A) Pending transaction in mempool (blockNumber is None) -> TRANSACTION_PENDING without failure.
    B) Dropped/not-found transaction -> TRANSACTION_DROPPED_OR_NOT_FOUND, marks RECONCILIATION_REQUIRED.
    C) Reverted transaction (status 0x0) -> TRANSFER_TRANSACTION_REVERTED, marks FAILED.
    """
    uid = uuid.uuid4().hex[:6]
    ev_id = f"EV-8C-010-{uid}"
    register_evidence_on_chain(ev_id, "0" * 64)

    durable_tx = asyncio.run(create_durable_transaction(
        evidence_id=ev_id,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Lifecycle status test",
        idempotency_key=f"IDEM-8C-010-{uid}"
    ))
    tx_id = durable_tx["transaction_id"]
    asyncio.run(update_transaction_state(
        tx_id,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "10" * 32}
    ))

    # Scenario A: Transaction is pending in mempool
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: (None, "RECEIPT_NOT_FOUND")
    )
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_by_hash",
        lambda h: ({"hash": h, "blockNumber": None}, None)
    )
    rec_a, tx_a, err_a = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert rec_a is False
    assert err_a == "TRANSACTION_PENDING"
    assert tx_a["status"] == CustodyTransactionStatus.SUBMITTED.value  # Not prematurely marked FAILED

    # Scenario B: Transaction dropped / absent from mempool
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_by_hash",
        lambda h: (None, "TX_NOT_FOUND")
    )
    rec_b, tx_b, err_b = asyncio.run(reconcile_durable_transaction(tx_id, allow_offline_fallback=True))
    assert rec_b is False
    assert err_b == "TRANSACTION_DROPPED_OR_NOT_FOUND"
    assert tx_b["status"] == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value

    # Scenario C: Transaction reverted on-chain
    ev_id_c = f"EV-8C-010C-{uid}"
    register_evidence_on_chain(ev_id_c, "0" * 64)
    durable_tx_c = asyncio.run(create_durable_transaction(
        evidence_id=ev_id_c,
        actor_id="investigator1",
        new_custodian="officer2",
        reason="Revert test"
    ))
    tx_id_c = durable_tx_c["transaction_id"]
    asyncio.run(update_transaction_state(
        tx_id_c,
        CustodyTransactionStatus.SUBMITTED,
        {"transfer_tx_hash": "0x" + "13" * 32}
    ))
    monkeypatch.setattr(
        "app.services.custody_transaction.get_transaction_receipt",
        lambda h: ({"status": "0x0", "blockNumber": 1000}, "TRANSACTION_REVERTED")
    )
    rec_c, tx_c, err_c = asyncio.run(reconcile_durable_transaction(tx_id_c, allow_offline_fallback=True))
    assert rec_c is False
    assert err_c == "TRANSFER_TRANSACTION_REVERTED"
    assert tx_c["status"] == CustodyTransactionStatus.FAILED.value
