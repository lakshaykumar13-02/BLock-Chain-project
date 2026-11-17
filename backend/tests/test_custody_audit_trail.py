"""
ChainVault Phase 2 — Tamper-Evident Custody Audit Trail Test Suite
==================================================================
Mandatory Automated Negative & Regression Tests (Section 12):
1.  Test 1: Valid multi-event custody history with correct predecessor links (VERIFIED).
2.  Test 2: Event content modification without updating event hash (TAMPERED).
3.  Test 3: Previous-event hash modification / broken predecessor link (TAMPERED).
4.  Test 4: Middle event deletion / sequence gap detection (INCONSISTENT).
5.  Test 5: Event reordering detection (INCONSISTENT).
6.  Test 6: Duplicate event ID or sequence number insertion (INCONSISTENT).
7.  Test 7: Stored event hash manipulation (TAMPERED).
8.  Test 8: Blockchain anchor mismatch (TAMPERED / mismatch reported, never VERIFIED).
9.  Test 9: Missing or unavailable blockchain RPC node (UNAVAILABLE / fails closed).
10. Test 10: Role-based authorization & restriction of custody mutations.
11. Test 11: Concurrent custody events serialization & conflict prevention.
12. Test 12: Full regression and API contract validation.
"""

import io
import os
import copy
import asyncio
import hashlib
import datetime
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import AUDIT_LOGS_STORE
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    register_evidence_on_chain
)
from app.services.audit_trail import (
    record_custody_event,
    verify_custody_audit_trail,
    calculate_canonical_event_hash,
    get_stored_custody_events,
    persist_custody_event
)

client = TestClient(app)


def get_test_token(username="investigator1"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def cleanup_audit_synthetic_records():
    """Ensure all synthetic test records are cleaned up after each test."""
    synthetic_ids = [
        "EV-AUD-001", "EV-AUD-002", "EV-AUD-003", "EV-AUD-004",
        "EV-AUD-005", "EV-AUD-006", "EV-AUD-007", "EV-AUD-008",
        "EV-AUD-009", "EV-AUD-010", "EV-AUD-011", "EV-AUD-012"
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


# -----------------------------------------------------------------------------
# TEST 1 — Valid History (VERIFIED)
# -----------------------------------------------------------------------------
def test_01_valid_multi_event_custody_history_verified():
    """
    Test 1: Valid history
    Create a valid multi-event custody history with correct predecessor links.
    Expected: VERIFIED.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-001"
    payload = b"Valid Custody Artifact 001"
    file_hash = hashlib.sha256(payload).hexdigest()

    # Step A: Ingest evidence (Genesis event created)
    files = {"file": ("artifact_001.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-001"}, headers=headers)
    assert up_res.status_code == 201

    # Step B: Register on-chain
    reg_res = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-AUD-001"}, headers=headers)
    assert reg_res.status_code == 200

    # Step C: Transfer custody (Event 3)
    t1_res = client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "Transfer to forensics lab"}, headers=headers)
    assert t1_res.status_code == 200

    # Step D: Transfer custody again (Event 4)
    t2_res = client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "investigator1", "reason": "Return to primary investigator"}, headers=headers)
    assert t2_res.status_code == 200

    # Step E: Verify audit trail
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["status"] == "success"
    assert res["verification_status"] == "VERIFIED"
    assert res["verified"] is True
    assert res["tampered"] is False
    assert res["chain_intact"] is True
    assert res["event_count"] >= 3
    assert res["failure_reason"] is None

    # Inspect event links
    events = res["events"]
    assert events[0]["sequence_number"] == 1
    assert events[0]["previous_event_hash"] == "GENESIS"
    assert events[0]["hash_valid"] is True
    assert events[0]["link_valid"] is True

    for i in range(1, len(events)):
        assert events[i]["sequence_number"] == events[i - 1]["sequence_number"] + 1
        assert events[i]["previous_event_hash"] == events[i - 1]["stored_event_hash"]
        assert events[i]["hash_valid"] is True
        assert events[i]["link_valid"] is True


# -----------------------------------------------------------------------------
# TEST 2 — Event Content Modification (TAMPERED)
# -----------------------------------------------------------------------------
def test_02_event_content_modification_tampered():
    """
    Test 2: Event content modification
    Change a stored event field without updating its event hash.
    Expected: TAMPERED.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-002"
    payload = b"Payload for Modification Test 002"

    files = {"file": ("artifact_002.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-002"}, headers=headers)
    assert up_res.status_code == 201

    t1_res = client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "Initial transfer"}, headers=headers)
    assert t1_res.status_code == 200

    # Maliciously modify the action and actor in stored event 2
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 2
    events[1]["actor_id"] = "rogue_attacker"
    events[1]["action"] = "UNAUTHORIZED_CUSTODY_HIJACK"

    # Verify audit trail
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "EVENT_HASH_MISMATCH"
    assert "Event content modification detected" in res["failure_reason"]


# -----------------------------------------------------------------------------
# TEST 3 — Previous-Event Hash Modification (TAMPERED)
# -----------------------------------------------------------------------------
def test_03_previous_event_hash_modification_broken_chain():
    """
    Test 3: Previous-event hash modification
    Change a predecessor link in a synthetic stored event.
    Expected: Broken chain detected; TAMPERED.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-003"
    payload = b"Payload for Predecessor Link Test 003"

    files = {"file": ("artifact_003.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-003"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "officer2", "reason": "Transfer 1"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst3", "reason": "Transfer 2"}, headers=headers)

    # Maliciously alter the predecessor link of event 3
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 3
    fake_prev_hash = "deadbeef" * 8
    events[2]["previous_event_hash"] = fake_prev_hash
    # Also update event_hash to isolate the broken predecessor check
    events[2]["event_hash"] = calculate_canonical_event_hash(events[2])

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "BROKEN_PREDECESSOR_LINK"
    assert "Broken predecessor hash link" in res["failure_reason"]


# -----------------------------------------------------------------------------
# TEST 4 — Event Deletion (INCONSISTENT)
# -----------------------------------------------------------------------------
def test_04_middle_event_deletion_detected():
    """
    Test 4: Event deletion
    Delete a middle event from a disposable test history.
    Expected: Missing sequence, broken predecessor link, or checkpoint mismatch detected.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-004"
    payload = b"Payload for Event Deletion Test 004"

    files = {"file": ("artifact_004.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-004"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "officer2", "reason": "Transfer 1"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst3", "reason": "Transfer 2"}, headers=headers)

    # Delete middle event (index 1)
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 3
    del events[1]

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] in ["INCONSISTENT", "TAMPERED"]
    assert res["verified"] is False
    assert res["technical_error"] in ["SEQUENCE_GAP_DETECTED", "BROKEN_PREDECESSOR_LINK"]


# -----------------------------------------------------------------------------
# TEST 5 — Event Reordering (INCONSISTENT)
# -----------------------------------------------------------------------------
def test_05_event_reordering_detected():
    """
    Test 5: Event reordering
    Reorder events without changing their sequence and predecessor relationships.
    Expected: The verifier detects the ordering inconsistency.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-005"
    payload = b"Payload for Event Reordering Test 005"

    files = {"file": ("artifact_005.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-005"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "officer2", "reason": "Transfer 1"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst3", "reason": "Transfer 2"}, headers=headers)

    # Swap sequence 2 and sequence 3
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 3
    events[1], events[2] = events[2], events[1]

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] in ["EVENT_REORDERING_DETECTED", "SEQUENCE_GAP_DETECTED"]


# -----------------------------------------------------------------------------
# TEST 6 — Duplicate Event ID or Sequence (INCONSISTENT)
# -----------------------------------------------------------------------------
def test_06_duplicate_event_id_or_sequence_fails():
    """
    Test 6: Duplicate event ID or sequence
    Insert a duplicate identifier or conflicting sequence in the isolated test store.
    Expected: Audit verification fails.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-006"
    payload = b"Payload for Duplicate Event Test 006"

    files = {"file": ("artifact_006.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-006"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "officer2", "reason": "Transfer 1"}, headers=headers)

    # Duplicate sequence number in event 2
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 2
    dup_event = copy.deepcopy(events[1])
    dup_event["event_id"] = "EVT-DUP-UNIQUE-ID"
    # Keep identical sequence_number
    dup_event["sequence_number"] = events[1]["sequence_number"]
    events.append(dup_event)

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "DUPLICATE_SEQUENCE_NUMBER"


# -----------------------------------------------------------------------------
# TEST 7 — Stored Event Hash Manipulation (TAMPERED)
# -----------------------------------------------------------------------------
def test_07_stored_event_hash_manipulation_tampered():
    """
    Test 7: MongoDB event hash manipulation
    Modify a stored event hash or event content in the isolated database.
    Expected: The recalculated hash or trusted checkpoint comparison detects the mismatch.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-007"
    payload = b"Payload for Hash Manipulation Test 007"

    files = {"file": ("artifact_007.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-007"}, headers=headers)

    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 1

    # Directly alter stored event_hash
    tampered_hash = hashlib.sha256(b"MALICIOUS_FORGED_EVENT_HASH").hexdigest()
    events[0]["event_hash"] = tampered_hash

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "EVENT_HASH_MISMATCH"


# -----------------------------------------------------------------------------
# TEST 8 — Blockchain Anchor Mismatch
# -----------------------------------------------------------------------------
def test_08_blockchain_anchor_mismatch_never_verified():
    """
    Test 8: Blockchain anchor mismatch
    Use an isolated test scenario where the stored audit commitment differs from
    the independently retrieved blockchain anchor.
    Expected: The mismatch is reported and never shown as VERIFIED.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-008"
    payload = b"Authentic Payload 008"
    file_hash = hashlib.sha256(payload).hexdigest()

    files = {"file": ("artifact_008.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-008"}, headers=headers)

    # Register original hash on-chain
    client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-AUD-008"}, headers=headers)

    # Alter the genesis event's recorded file_hash in database and recompute the hash chain
    # (Attacker rewrites entire chain to make it internally consistent, but blockchain anchor catches it!)
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 1
    events[0]["details"]["file_hash"] = hashlib.sha256(b"ALTERED_SPECIMEN_HASH").hexdigest()
    events[0]["event_hash"] = calculate_canonical_event_hash(events[0])
    for i in range(1, len(events)):
        events[i]["previous_event_hash"] = events[i - 1]["event_hash"]
        events[i]["event_hash"] = calculate_canonical_event_hash(events[i])

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] in ["TAMPERED", "INCONSISTENT"]
    assert res["verified"] is False
    assert res["technical_error"] == "BLOCKCHAIN_ANCHOR_MISMATCH"
    assert "does not match immutable blockchain anchor" in res["failure_reason"]


# -----------------------------------------------------------------------------
# TEST 9 — Missing or Unavailable Blockchain (Fails Closed)
# -----------------------------------------------------------------------------
def test_09_blockchain_unavailable_fails_closed(monkeypatch):
    """
    Test 9: Missing or unavailable blockchain
    Simulate an unavailable RPC or missing required anchor.
    Expected: An explicit unavailable or inconsistent result, never a false success.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-009"
    payload = b"Payload for Offline Blockchain Test 009"

    files = {"file": ("artifact_009.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-009"}, headers=headers)

    # Monkeypatch get_independent_blockchain_record to simulate RPC failure
    def mock_rpc_down(evidence_id, allow_offline_fallback=False):
        return None, "RPC_UNAVAILABLE"

    monkeypatch.setattr(
        "app.services.audit_trail.get_independent_blockchain_record",
        mock_rpc_down
    )

    # When require_blockchain=True, must return UNAVAILABLE
    v_res = client.get(f"/api/audit/verify/{ev_id}?require_blockchain=true", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "UNAVAILABLE"
    assert res["verified"] is False
    assert res["technical_error"] == "BLOCKCHAIN_RPC_UNAVAILABLE"


# -----------------------------------------------------------------------------
# TEST 10 — Authorization & RBAC
# -----------------------------------------------------------------------------
def test_10_authorization_and_rbac_custody_protection():
    """
    Test 10: Authorization
    Verify that unauthorized users cannot create, modify, delete, or inspect
    restricted custody events outside their existing permissions.
    """
    viewer_token = get_test_token("viewer1")
    headers_viewer = {"Authorization": f"Bearer {viewer_token}"}
    ev_id = "EV-AUD-010"

    # 1. VIEWER cannot execute custody transfer (Must return HTTP 403 Forbidden)
    res_transfer = client.post(
        "/api/custody/transfer",
        json={"evidence_id": ev_id, "new_custodian": "viewer1", "reason": "Unauthorized transfer"},
        headers=headers_viewer
    )
    assert res_transfer.status_code == 403

    # 2. VIEWER cannot access all audit logs across all cases (/api/audit/all)
    res_all = client.get("/api/audit/all", headers=headers_viewer)
    assert res_all.status_code == 403

    # 3. Unauthenticated requests are rejected (401 Unauthorized)
    res_noauth = client.post("/api/custody/transfer", json={"evidence_id": ev_id})
    assert res_noauth.status_code == 401

    # 4. Deletion of audit logs is completely rejected (404/405 - no deletion route exists)
    res_del = client.delete(f"/api/audit/logs/{ev_id}", headers=headers_viewer)
    assert res_del.status_code in [404, 405]


# -----------------------------------------------------------------------------
# TEST 11 — Concurrent Events Serialization
# -----------------------------------------------------------------------------
def test_11_concurrent_custody_events_serialization():
    """
    Test 11: Concurrent events
    Test concurrent requests for the same evidence where practical.
    Expected: No silent branching, duplicate sequence assignment, or overwritten event history.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-011"
    payload = b"Payload for Concurrency Serialization Test 011"

    files = {"file": ("artifact_011.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-011"}, headers=headers)

    # Concurrently issue 4 custody transfers
    import concurrent.futures

    def do_transfer(custodian_name):
        return client.post(
            "/api/custody/transfer",
            json={"evidence_id": ev_id, "new_custodian": custodian_name, "reason": f"Handover to {custodian_name}"},
            headers=headers
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(do_transfer, f"officer_batch_{i}")
            for i in range(4)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r.status_code == 200

    # Retrieve history
    hist_res = client.get(f"/api/custody/history/{ev_id}", headers=headers)
    assert hist_res.status_code == 200
    events = hist_res.json()

    # Total events: 1 (genesis) + 4 (transfers) = 5
    assert len(events) == 5

    # Sequences must be strictly 1, 2, 3, 4, 5 without duplicates or branches
    sequences = [ev["sequence_number"] for ev in events]
    assert sequences == [1, 2, 3, 4, 5]

    # Predecessor hash chain must be verified
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    assert v_res.json()["verification_status"] == "VERIFIED"
    assert v_res.json()["chain_intact"] is True


# -----------------------------------------------------------------------------
# TEST 12 — Regression & Determinism
# -----------------------------------------------------------------------------
def test_12_regression_and_api_contract():
    """
    Test 12: Regression
    1. Validates POST /api/audit/verify body input.
    2. Confirms that verification queries NEVER mutate stored database or chain records.
    3. Confirms deterministic canonical hashing across multiple executions.
    """
    token = get_test_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = "EV-AUD-012"
    payload = b"Payload for Regression Test 012"

    files = {"file": ("artifact_012.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-AUD-012"}, headers=headers)

    # 1. POST /api/audit/verify
    post_res = client.post("/api/audit/verify", json={"evidence_id": ev_id}, headers=headers)
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["verification_status"] == "VERIFIED"

    # 2. Immutability: Verify stored events are never mutated by verification calls
    events_before = copy.deepcopy(AUDIT_LOGS_STORE[ev_id])
    for _ in range(3):
        client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    events_after = AUDIT_LOGS_STORE[ev_id]
    assert events_before == events_after

    # 3. Deterministic canonical hash
    canonical_hash1 = calculate_canonical_event_hash(events_before[0])
    canonical_hash2 = calculate_canonical_event_hash(events_after[0])
    assert canonical_hash1 == canonical_hash2
    assert canonical_hash1 == events_before[0]["event_hash"]
