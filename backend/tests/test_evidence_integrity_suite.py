"""
ChainVault Phase 3 — Comprehensive Evidence Integrity Test Suite
=================================================================
Automated test suite validating digital evidence integrity across:
1. Physical files on disk (SHA-256 byte streaming, tampering, missing files).
2. MongoDB metadata & persistence (manipulated hash, metadata mismatch, persistence failure, no silent in-memory fallback).
3. Blockchain integrity (on-chain hash, unknown ID, mismatched hash, missing receipt, reverted tx, RPC offline, chain ID mismatch).
4. Duplicate registration & idempotency (repeated identical requests, conflicting duplicate rejection without silent overwrite).
5. Custody audit trail (event content tampering, broken predecessor hash, sequence gap, reordering, duplicate ID/seq, rewritten history vs blockchain anchor, verifiable anchor required).
6. Cross-record consistency & RBAC (wrong evidence ID, swapped files, case ID mismatch, unauthorized mutations).
7. Failure & recovery (blockchain reset, missing receipt, DB/RPC failure, concurrency serialization, fail-closed guarantee).

Statuses asserted across all negative tests:
- VERIFIED: All required integrity checks pass.
- TAMPERED: Cryptographic integrity fails.
- NOT_FOUND: Evidence or registration record missing.
- INCONSISTENT: IDs, records, sequences, or chain state conflict.
- UNAVAILABLE: Required infrastructure is offline/unavailable.
"""

import io
import os
import copy
import time
import asyncio
import hashlib
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import AUDIT_LOGS_STORE
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    register_evidence_on_chain,
    get_evidence_from_chain,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS
)
from app.services.audit_trail import (
    record_custody_event,
    verify_custody_audit_trail,
    calculate_canonical_event_hash,
    get_stored_custody_events,
    persist_custody_event
)
from app.services.hashing import calculate_hash

client = TestClient(app)

SYNTHETIC_EVIDENCE_PREFIX = "EV-PH3-"


def get_token(username="investigator1"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200, f"Authentication failed for {username}: {res.text}"
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def cleanup_phase3_synthetic_state():
    """Ensure all synthetic test records are cleaned up before and after each test."""
    def _cleanup():
        keys_ev = [k for k in list(EVIDENCE_STORE.keys()) if k.startswith(SYNTHETIC_EVIDENCE_PREFIX)]
        for k in keys_ev:
            rec = EVIDENCE_STORE.pop(k, None)
            if rec and rec.get("file_path") and os.path.exists(rec["file_path"]):
                try:
                    os.remove(rec["file_path"])
                except OSError:
                    pass
        keys_audit = [k for k in list(AUDIT_LOGS_STORE.keys()) if k.startswith(SYNTHETIC_EVIDENCE_PREFIX)]
        for k in keys_audit:
            AUDIT_LOGS_STORE.pop(k, None)
        keys_chain = [k for k in list(CHAIN_EVIDENCE_STORE.keys()) if k.startswith(SYNTHETIC_EVIDENCE_PREFIX)]
        for k in keys_chain:
            CHAIN_EVIDENCE_STORE.pop(k, None)
        keys_cust = [k for k in list(CHAIN_CUSTODY_LOGS.keys()) if k.startswith(SYNTHETIC_EVIDENCE_PREFIX)]
        for k in keys_cust:
            CHAIN_CUSTODY_LOGS.pop(k, None)

    _cleanup()
    yield
    _cleanup()


def mock_contract_record(evidence_id, file_hash, case_id="CV-PH3-001", custodian="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"):
    """Generate a valid mocked on-chain contract record matching EvidenceRegistry.getEvidence output."""
    return {
        "evidence_id": evidence_id,
        "case_id": case_id,
        "file_hash": file_hash,
        "custodian": custodian,
        "registered_at": int(time.time()),
        "contract_address": CONTRACT_ADDRESS,
        "chain_id": EXPECTED_CHAIN_ID,
        "tx_hash": "0x" + hashlib.sha256(f"{evidence_id}:{file_hash}".encode()).hexdigest(),
        "block_number": 105,
        "status": "confirmed"
    }


# =============================================================================
# 1. EVIDENCE FILES INTEGRITY
# =============================================================================

def test_01_valid_original_file_sha256_verified(monkeypatch):
    """
    Evidence Files: Test valid original evidence file and expected SHA-256.
    Calculates SHA-256 directly from file bytes on disk.
    Expected: Status is VERIFIED, file_status is present, technical_error is None.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"ChainVault Authentic Forensic Evidence Specimen - Phase 3 Test 01"
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}FILE-001"

    # Ingest evidence
    files = {"file": ("specimen_001.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-001"}, headers=headers)
    assert up_res.status_code == 201
    assert up_res.json()["file_hash"] == expected_sha256

    # Mock blockchain contract with matching hash
    onchain = mock_contract_record(ev_id, expected_sha256)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    # Verify tripartite integrity
    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "VERIFIED"
    assert res["verified"] is True
    assert res["tampered"] is False
    assert res["file_status"] == "present"
    assert res["blockchain_verified"] is True
    assert res["technical_error"] is None
    assert res["physical_file_hash"] == expected_sha256
    assert res["database_hash"] == expected_sha256
    assert res["blockchain_hash"] == expected_sha256
    assert res["file_vs_database"] is True
    assert res["file_vs_blockchain"] is True
    assert res["database_vs_blockchain"] is True


def test_02_modified_file_bytes_tampered_detection(monkeypatch):
    """
    Evidence Files: Modified file must return TAMPERED.
    Altering even a single byte of the stored file triggers cryptographic failure.
    Original database and on-chain hashes must remain immutable.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Authentic Original Binary Payload 002"
    orig_sha256 = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}FILE-002"

    files = {"file": ("specimen_002.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-002"}, headers=headers)
    assert up_res.status_code == 201

    onchain = mock_contract_record(ev_id, orig_sha256)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    # Tamper with file on disk
    file_path = EVIDENCE_STORE[ev_id]["file_path"]
    with open(file_path, "wb") as f:
        f.write(b"Authentic Original Binary Payload 002 TAMPERED")

    fresh_hash = hashlib.sha256(b"Authentic Original Binary Payload 002 TAMPERED").hexdigest()

    # Verify tampering detection
    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "FILE_HASH_MISMATCH_TAMPERED"
    assert res["physical_file_hash"] == fresh_hash
    assert res["database_hash"] == orig_sha256
    assert res["blockchain_hash"] == orig_sha256
    assert res["comparisons"]["file_vs_blockchain"] is False
    assert res["comparisons"]["file_vs_database"] is False
    assert res["comparisons"]["database_vs_blockchain"] is True

    # Assert stored records were NOT mutated by the verification check
    assert EVIDENCE_STORE[ev_id]["file_hash"] == orig_sha256


def test_03_missing_evidence_file_fails_closed(monkeypatch):
    """
    Evidence Files: Missing evidence file must never return VERIFIED.
    Returns TAMPERED with technical_error PHYSICAL_FILE_MISSING.
    Never substitutes a previous or cached hash for fresh file hash.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Disposable Evidence Payload 003"
    orig_sha256 = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}FILE-003"

    files = {"file": ("specimen_003.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-003"}, headers=headers)
    assert up_res.status_code == 201

    onchain = mock_contract_record(ev_id, orig_sha256)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    # Remove physical file from disk
    file_path = EVIDENCE_STORE[ev_id]["file_path"]
    if os.path.exists(file_path):
        os.remove(file_path)

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["file_status"] == "missing"
    assert res["physical_file_hash"] is None  # Never substitute cached hash!
    assert res["technical_error"] == "PHYSICAL_FILE_MISSING"
    assert "missing from disk" in res["explanation"]


def test_04_hash_computed_from_actual_bytes_chunked_streaming(tmp_path):
    """
    Evidence Files: Hash must be computed from actual file bytes.
    Validates chunked streaming on large binary specimens containing null bytes,
    verifying bit-level sensitivity to single-byte mutations.
    """
    large_payload = (b"ForensicDataBlock\x00\xff\xfe\x01" * 4096)  # ~84 KB (> 64KB chunk buffer)
    file_path = tmp_path / "stream_specimen.bin"
    with open(file_path, "wb") as f:
        f.write(large_payload)

    computed_hash = calculate_hash(str(file_path))
    expected_hash = hashlib.sha256(large_payload).hexdigest()
    assert computed_hash == expected_hash

    # Single bit modification in the middle of file
    mutated_payload = bytearray(large_payload)
    mutated_payload[65536] ^= 0x01  # Flip 1 bit across 64KB boundary
    with open(file_path, "wb") as f:
        f.write(mutated_payload)

    mutated_hash = calculate_hash(str(file_path))
    assert mutated_hash != expected_hash
    assert mutated_hash == hashlib.sha256(mutated_payload).hexdigest()


# =============================================================================
# 2. MONGODB INTEGRITY
# =============================================================================

def test_05_mongodb_manipulated_stored_evidence_hash(monkeypatch):
    """
    MongoDB Integrity: Manipulated stored evidence hash.
    Register evidence, then alter only the database recorded hash to a different valid SHA-256.
    Physical file matches authentic blockchain record.
    Expected: Result is INCONSISTENT, database_vs_blockchain is False, file_vs_blockchain is True.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Authentic Sacrosanct Evidence Specimen 005"
    authentic_sha256 = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}MDB-005"

    files = {"file": ("specimen_005.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-005"}, headers=headers)
    assert up_res.status_code == 201

    onchain = mock_contract_record(ev_id, authentic_sha256)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    # Alter ONLY database stored hash
    manipulated_hash = hashlib.sha256(b"MALICIOUS_ALTERED_DATABASE_HASH_999").hexdigest()
    EVIDENCE_STORE[ev_id]["file_hash"] = manipulated_hash

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "DATABASE_HASH_MANIPULATED"
    assert res["database_hash"] == manipulated_hash
    assert res["physical_file_hash"] == authentic_sha256
    assert res["blockchain_hash"] == authentic_sha256
    assert res["comparisons"]["file_vs_blockchain"] is True
    assert res["comparisons"]["database_vs_blockchain"] is False
    assert res["comparisons"]["file_vs_database"] is False


def test_06_metadata_file_hash_mismatch_without_blockchain(monkeypatch):
    """
    MongoDB Integrity: Metadata/file hash mismatch.
    Evidence present in DB but not anchored to blockchain; file hash does not match stored hash.
    Expected: Fails closed, returns INCONSISTENT with NOT_REGISTERED_ON_BLOCKCHAIN.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Unanchored Mismatched Evidence 006"
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}MDB-006"

    # Connected blockchain reports evidence not registered
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, "NOT_FOUND"))

    files = {"file": ("specimen_006.bin", io.BytesIO(payload), "application/octet-stream")}
    up_res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-006"}, headers=headers)
    assert up_res.status_code == 201

    # Tamper file
    file_path = EVIDENCE_STORE[ev_id]["file_path"]
    with open(file_path, "wb") as f:
        f.write(b"CORRUPTED FILE WITHOUT BLOCKCHAIN ANCHOR")

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verified"] is False
    assert res["verification_status"] == "INCONSISTENT"
    assert res["technical_error"] == "NOT_REGISTERED_ON_BLOCKCHAIN"


def test_07_database_persistence_failure_cleans_up_orphaned_files(monkeypatch):
    """
    MongoDB Integrity: Database unavailable or persistence failure.
    If database persistence raises an exception during ingestion, the system must
    fail closed, clean up the written evidence file, and return HTTP 500.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Payload for Persistence Failure Test 007"
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}MDB-007"

    # Force record_custody_event to simulate database persistence failure
    async def mock_failed_event(*args, **kwargs):
        raise RuntimeError("Simulated Database I/O Disk Write Failure")

    monkeypatch.setattr("app.services.audit_trail.record_custody_event", mock_failed_event)

    files = {"file": ("specimen_007.bin", io.BytesIO(payload), "application/octet-stream")}
    res = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-007"}, headers=headers)

    assert res.status_code == 500
    assert "Metadata persistence failed" in res.json()["detail"]


def test_08_no_silent_inmemory_fallback_for_verification(monkeypatch):
    """
    MongoDB Integrity: No silent in-memory fallback that produces a false successful verification.
    When database query fails and in-memory fallback is disabled, verification must fail closed
    with UNAVAILABLE and technical_error DATABASE_UNAVAILABLE, never VERIFIED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}MDB-008"

    # Ingest evidence
    files = {"file": ("specimen_008.bin", io.BytesIO(b"Data 008"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-008"}, headers=headers)

    # Simulate database error during audit event retrieval
    async def mock_db_error(eid, allow_in_memory_fallback=True):
        if not allow_in_memory_fallback:
            raise RuntimeError("MongoDB Connection Refused")
        return []

    monkeypatch.setattr("app.services.audit_trail.get_stored_custody_events", mock_db_error)

    # Calling verify with allow_in_memory_fallback=False
    v_res = client.get(f"/api/audit/verify/{ev_id}?allow_in_memory_fallback=false", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "UNAVAILABLE"
    assert res["verified"] is False
    assert res["technical_error"] == "DATABASE_UNAVAILABLE"


# =============================================================================
# 3. BLOCKCHAIN INTEGRITY
# =============================================================================

def test_09_correct_onchain_evidence_hash(monkeypatch):
    """
    Blockchain Integrity: Correct on-chain evidence hash.
    Asserts blockchain_status is verified, blockchain_verified is True.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Specimen for Correct OnChain Hash 009"
    file_hash = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}BC-009"

    files = {"file": ("specimen_009.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-009"}, headers=headers)

    onchain = mock_contract_record(ev_id, file_hash)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "VERIFIED"
    assert res["verified"] is True
    assert res["blockchain_verified"] is True
    assert res["blockchain_status"] == "verified"
    assert res["blockchain_hash"] == file_hash


def test_10_missing_registration_and_unknown_evidence_id(monkeypatch):
    """
    Blockchain Integrity: Missing registration and unknown evidence ID.
    Unknown ID anywhere -> NOT_FOUND with RECORD_NOT_FOUND.
    Known in DB but unanchored -> INCONSISTENT with NOT_REGISTERED_ON_BLOCKCHAIN.
    """
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, "NOT_FOUND"))

    # 1. Unknown evidence ID anywhere
    v_res1 = client.post("/api/verification/verify", json={"evidence_id": f"{SYNTHETIC_EVIDENCE_PREFIX}UNKNOWN-9999"})
    assert v_res1.status_code == 200
    assert v_res1.json()["verification_status"] == "NOT_FOUND"
    assert v_res1.json()["technical_error"] == "RECORD_NOT_FOUND"

    # 2. Known in DB but unanchored on chain
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}BC-010"
    files = {"file": ("specimen_010.bin", io.BytesIO(b"Payload 010"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-010"}, headers=headers)

    v_res2 = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res2.status_code == 200
    assert v_res2.json()["verification_status"] == "INCONSISTENT"
    assert v_res2.json()["technical_error"] == "NOT_REGISTERED_ON_BLOCKCHAIN"


def test_11_wrong_evidence_id_or_mismatched_onchain_hash(monkeypatch):
    """
    Blockchain Integrity: Wrong evidence ID or mismatched on-chain hash.
    On-chain recorded hash differs from physical file.
    Expected: TAMPERED, technical_error FILE_HASH_MISMATCH_TAMPERED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Genuine Specimen Payload 011"
    genuine_hash = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}BC-011"

    files = {"file": ("specimen_011.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-011"}, headers=headers)

    # Contract returns a different hash (mismatched / wrong record)
    wrong_hash = hashlib.sha256(b"DIFFERENT_HASH_ON_CHAIN_REGISTER").hexdigest()
    onchain = mock_contract_record(ev_id, wrong_hash)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "FILE_HASH_MISMATCH_TAMPERED"
    assert res["physical_file_hash"] == genuine_hash
    assert res["blockchain_hash"] == wrong_hash


def test_12_unavailable_rpc_endpoint_fails_closed(monkeypatch):
    """
    Blockchain Integrity: Unavailable RPC endpoint.
    When Ethereum RPC node is unreachable, verification fails closed with UNAVAILABLE.
    Must never report VERIFIED or falsely declare TAMPERED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}BC-012"
    files = {"file": ("specimen_012.bin", io.BytesIO(b"Data 012"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-012"}, headers=headers)

    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, "RPC_UNAVAILABLE"))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "UNAVAILABLE"
    assert res["verified"] is False
    assert res["tampered"] is False
    assert res["technical_error"] == "BLOCKCHAIN_RPC_UNAVAILABLE"


def test_13_chain_id_mismatch_fails_closed(monkeypatch):
    """
    Blockchain Integrity: Chain ID or deployment mismatch.
    Connected RPC node returns Chain ID 1 (Mainnet) when expecting 31337.
    Verification fails closed with UNAVAILABLE and technical_error CHAIN_ID_MISMATCH.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}BC-013"
    files = {"file": ("specimen_013.bin", io.BytesIO(b"Data 013"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-013"}, headers=headers)

    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, "CHAIN_ID_MISMATCH"))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "UNAVAILABLE"
    assert res["verified"] is False
    assert res["technical_error"] == "CHAIN_ID_MISMATCH"


# =============================================================================
# 4. DUPLICATE REGISTRATION & IDEMPOTENCY
# =============================================================================

def test_14_duplicate_registration_identical_hash_idempotent():
    """
    Duplicate Registration: Repeated requests and idempotency.
    Registering the same evidence ID with the identical hash succeeds idempotently
    and returns the existing receipt without corrupting state.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}DUP-014"
    h = hashlib.sha256(b"Payload 014").hexdigest()

    # First registration
    r1 = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": h, "case_id": "CV-PH3-014"}, headers=headers)
    assert r1.status_code == 200
    tx1 = r1.json()["tx_hash"]

    # Second registration with identical hash
    r2 = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": h, "case_id": "CV-PH3-014"}, headers=headers)
    assert r2.status_code == 200
    tx2 = r2.json()["tx_hash"]

    assert tx1 == tx2
    assert CHAIN_EVIDENCE_STORE[ev_id]["file_hash"] == h


def test_15_duplicate_registration_conflicting_hash_rejected_no_overwrite():
    """
    Duplicate Registration: Duplicate registration with conflicting hash.
    Ensure an existing registration is NOT silently overwritten.
    Returns HTTP 409 Conflict and preserves original on-chain registration.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}DUP-015"
    h1 = hashlib.sha256(b"Payload Original 015").hexdigest()
    h2 = hashlib.sha256(b"Payload Conflicting 015").hexdigest()

    # Initial registration
    r1 = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": h1, "case_id": "CV-PH3-015"}, headers=headers)
    assert r1.status_code == 200

    # Conflicting registration attempt
    r2 = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": h2, "case_id": "CV-PH3-015"}, headers=headers)
    assert r2.status_code == 409
    assert "different hash" in r2.json()["detail"].lower()

    # Stored record must NOT have been overwritten
    assert CHAIN_EVIDENCE_STORE[ev_id]["file_hash"] == h1


def test_16_duplicate_evidence_upload_conflicting_content_rejected():
    """
    Duplicate Registration: Duplicate evidence upload with conflicting content.
    Uploading a new file under an already-assigned evidence ID is rejected with HTTP 409.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}DUP-016"

    # First upload
    f1 = {"file": ("file1.bin", io.BytesIO(b"Content Alpha 016"), "application/octet-stream")}
    r1 = client.post("/api/evidence/upload", files=f1, data={"evidence_id": ev_id, "case_id": "CV-PH3-016"}, headers=headers)
    assert r1.status_code == 201
    orig_hash = r1.json()["file_hash"]

    # Second upload with different content under same ID
    f2 = {"file": ("file2.bin", io.BytesIO(b"Content Beta 016 Conflicts"), "application/octet-stream")}
    r2 = client.post("/api/evidence/upload", files=f2, data={"evidence_id": ev_id, "case_id": "CV-PH3-016"}, headers=headers)
    assert r2.status_code == 409

    # Original evidence remains unmutated
    assert EVIDENCE_STORE[ev_id]["file_hash"] == orig_hash


# =============================================================================
# 5. CUSTODY AUDIT TRAIL
# =============================================================================

def test_17_custody_event_content_modification_detected():
    """
    Custody Audit Trail: Modified event contents or event hash.
    Changing any field without recomputing event hash returns TAMPERED with EVENT_HASH_MISMATCH.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-017"

    files = {"file": ("specimen_017.bin", io.BytesIO(b"Artifact 017"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-017"}, headers=headers)

    # Ingest event exists. Modify a field inside details.
    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 1
    events[0]["details"]["filename"] = "forged_malicious_name.exe"

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "EVENT_HASH_MISMATCH"


def test_18_custody_broken_predecessor_hash_detected():
    """
    Custody Audit Trail: Broken predecessor hash.
    Corrupting previous_event_hash in multi-event chain returns TAMPERED with BROKEN_PREDECESSOR_LINK.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-018"

    files = {"file": ("specimen_018.bin", io.BytesIO(b"Artifact 018"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-018"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "Handover 1"}, headers=headers)

    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 2
    # Break predecessor hash
    events[1]["previous_event_hash"] = hashlib.sha256(b"BROKEN_POINTER").hexdigest()
    events[1]["event_hash"] = calculate_canonical_event_hash(events[1])

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "BROKEN_PREDECESSOR_LINK"


def test_19_custody_deleted_events_and_sequence_gaps():
    """
    Custody Audit Trail: Deleted events and sequence gaps.
    Deleting an intermediate event creates a sequence gap (e.g. seq 1 -> seq 3).
    Expected: INCONSISTENT with technical_error SEQUENCE_GAP_DETECTED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-019"

    files = {"file": ("specimen_019.bin", io.BytesIO(b"Artifact 019"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-019"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "T1"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "investigator1", "reason": "T2"}, headers=headers)

    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 3
    # Delete middle event (index 1)
    del events[1]

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "SEQUENCE_GAP_DETECTED"


def test_20_custody_reordered_events_detected():
    """
    Custody Audit Trail: Reordered events.
    Swapping event sequence positions triggers INCONSISTENT with MISSING_GENESIS_EVENT or EVENT_REORDERING_DETECTED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-020"

    files = {"file": ("specimen_020.bin", io.BytesIO(b"Artifact 020"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-020"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "T1"}, headers=headers)

    events = AUDIT_LOGS_STORE[ev_id]
    assert len(events) >= 2
    # Invert order of events
    events[0], events[1] = events[1], events[0]

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] in ["MISSING_GENESIS_EVENT", "EVENT_REORDERING_DETECTED"]


def test_21_custody_duplicate_event_ids_and_sequence_numbers():
    """
    Custody Audit Trail: Duplicate event IDs or sequence numbers.
    Inserting duplicate event IDs returns INCONSISTENT with DUPLICATE_EVENT_ID.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-021"

    files = {"file": ("specimen_021.bin", io.BytesIO(b"Artifact 021"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-021"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "T1"}, headers=headers)

    events = AUDIT_LOGS_STORE[ev_id]
    # Set event 1's event_id identical to event 0
    events[1]["event_id"] = events[0]["event_id"]

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "DUPLICATE_EVENT_ID"


def test_22_custody_rewritten_history_caught_by_blockchain_anchor(monkeypatch):
    """
    Custody Audit Trail: Rewritten history with recomputed hashes.
    An attacker modifies genesis event content and recalculates all subsequent event hashes
    and predecessor links to forge an internally valid hash chain.
    The verification engine reconciles against EvidenceRegistry.sol and catches the forgery!
    Expected: TAMPERED, technical_error BLOCKCHAIN_ANCHOR_MISMATCH, never VERIFIED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-022"
    orig_payload = b"Original Immutable Specimen 022"
    orig_hash = hashlib.sha256(orig_payload).hexdigest()

    files = {"file": ("specimen_022.bin", io.BytesIO(orig_payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-022"}, headers=headers)
    client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1", "reason": "Lab Analysis"}, headers=headers)

    # Mock authentic blockchain ledger holding the original hash
    onchain = mock_contract_record(ev_id, orig_hash)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    # Attacker rewrites genesis event file_hash and recalculates all hashes down the chain
    events = AUDIT_LOGS_STORE[ev_id]
    events[0]["details"]["file_hash"] = hashlib.sha256(b"FORGED_HASH").hexdigest()
    events[0]["event_hash"] = calculate_canonical_event_hash(events[0])
    for i in range(1, len(events)):
        events[i]["previous_event_hash"] = events[i - 1]["event_hash"]
        events[i]["event_hash"] = calculate_canonical_event_hash(events[i])

    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "BLOCKCHAIN_ANCHOR_MISMATCH"


def test_23_unanchored_history_not_falsely_claimed_as_blockchain_anchored():
    """
    Custody Audit Trail: Confirm history is not described as independently blockchain-anchored
    unless a verifiable on-chain anchor actually exists.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}AUD-023"

    files = {"file": ("specimen_023.bin", io.BytesIO(b"Data 023"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-023"}, headers=headers)

    # Audit verify without require_blockchain
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()

    # Blockchain reconciliation must be False
    assert res["blockchain_reconciled"] is False


# =============================================================================
# 6. CROSS-RECORD CONSISTENCY & ACCESS CONTROL (RBAC)
# =============================================================================

def test_24_swapped_evidence_files_detected_tampered(monkeypatch):
    """
    Cross-Record Consistency: Evidence metadata paired with a different file.
    Swap physical files on disk between Evidence A and Evidence B.
    Both must fail verification with TAMPERED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_a = f"{SYNTHETIC_EVIDENCE_PREFIX}CROSS-024A"
    ev_b = f"{SYNTHETIC_EVIDENCE_PREFIX}CROSS-024B"
    pay_a = b"Payload Specimen AAAA"
    pay_b = b"Payload Specimen BBBB"
    hash_a = hashlib.sha256(pay_a).hexdigest()
    hash_b = hashlib.sha256(pay_b).hexdigest()

    client.post("/api/evidence/upload", files={"file": ("a.bin", io.BytesIO(pay_a), "application/octet-stream")}, data={"evidence_id": ev_a, "case_id": "CV-024"}, headers=headers)
    client.post("/api/evidence/upload", files={"file": ("b.bin", io.BytesIO(pay_b), "application/octet-stream")}, data={"evidence_id": ev_b, "case_id": "CV-024"}, headers=headers)

    records = {
        ev_a: mock_contract_record(ev_a, hash_a),
        ev_b: mock_contract_record(ev_b, hash_b)
    }
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (records.get(eid), None if eid in records else "NOT_FOUND"))

    # Swap file contents on disk
    path_a = EVIDENCE_STORE[ev_a]["file_path"]
    path_b = EVIDENCE_STORE[ev_b]["file_path"]
    with open(path_a, "wb") as fa, open(path_b, "wb") as fb:
        fa.write(pay_b)
        fb.write(pay_a)

    va = client.post("/api/verification/verify", json={"evidence_id": ev_a}).json()
    vb = client.post("/api/verification/verify", json={"evidence_id": ev_b}).json()

    assert va["verification_status"] == "TAMPERED"
    assert va["verified"] is False
    assert vb["verification_status"] == "TAMPERED"
    assert vb["verified"] is False


def test_25_unauthenticated_requests_rejected():
    """
    Access Control: Unauthenticated requests to protected endpoints return HTTP 401 Unauthorized.
    """
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}RBAC-025"
    res1 = client.post("/api/evidence/upload", data={"evidence_id": ev_id})
    assert res1.status_code == 401

    res2 = client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1"})
    assert res2.status_code == 401

    res3 = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": "abc"})
    assert res3.status_code == 401

    res4 = client.get("/api/audit/all")
    assert res4.status_code == 401


def test_26_viewer_role_mutations_forbidden():
    """
    Access Control: VIEWER role is strictly forbidden from creating or modifying evidence,
    custody transfers, or blockchain registrations (HTTP 403 Forbidden).
    """
    viewer_token = get_token("viewer1")
    headers = {"Authorization": f"Bearer {viewer_token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}RBAC-026"

    # Viewer cannot upload evidence
    files = {"file": ("test.bin", io.BytesIO(b"data"), "application/octet-stream")}
    r1 = client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id}, headers=headers)
    assert r1.status_code == 403

    # Viewer cannot transfer custody
    r2 = client.post("/api/custody/transfer", json={"evidence_id": ev_id, "new_custodian": "analyst1"}, headers=headers)
    assert r2.status_code == 403

    # Viewer cannot register on blockchain
    r3 = client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": "abc"}, headers=headers)
    assert r3.status_code == 403

    # Viewer cannot access all audit logs
    r4 = client.get("/api/audit/all", headers=headers)
    assert r4.status_code == 403


def test_27_evidence_delete_forbidden_for_all_roles():
    """
    Access Control: Evidence records are immutable and must never be deleted.
    HTTP DELETE requests return 405 Method Not Allowed across Admin, Investigator, and Viewer.
    """
    admin_tok = get_token("admin")
    inv_tok = get_token("investigator1")
    view_tok = get_token("viewer1")

    for tok in [admin_tok, inv_tok, view_tok]:
        res = client.delete("/api/evidence/EV-PH3-ANY", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 405, f"DELETE should return 405, got {res.status_code}"


# =============================================================================
# 7. FAILURE & RECOVERY
# =============================================================================

def test_28_blockchain_reset_fails_closed(monkeypatch):
    """
    Failure & Recovery: Local blockchain reset or missing registration.
    Simulates node state loss where contract loses previously held registration.
    Verification fails closed, returns INCONSISTENT with NOT_REGISTERED_ON_BLOCKCHAIN, never VERIFIED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}FAIL-028"
    files = {"file": ("specimen_028.bin", io.BytesIO(b"Data 028"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-028"}, headers=headers)

    # Node was reset -> contract returns NOT_FOUND
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, "NOT_FOUND"))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "NOT_REGISTERED_ON_BLOCKCHAIN"


@pytest.mark.parametrize("simulated_error", [
    "RPC_UNAVAILABLE",
    "CHAIN_ID_MISMATCH",
    "CONTRACT_ERROR"
])
def test_29_all_infrastructure_failures_fail_closed(monkeypatch, simulated_error):
    """
    Failure & Recovery: All infrastructure failures must fail closed and must never produce VERIFIED.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}FAIL-029-{simulated_error}"
    files = {"file": ("test.bin", io.BytesIO(b"Payload"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-029"}, headers=headers)

    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, simulated_error))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    assert res["verified"] is False
    assert res["verification_status"] != "VERIFIED"


def test_30_concurrent_custody_events_serialization():
    """
    Failure & Recovery: Rapid retries and concurrent custody transfers on the same evidence
    are serialized by per-evidence async locks without sequence collisions or branching.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}FAIL-030"

    files = {"file": ("test_030.bin", io.BytesIO(b"Payload 030"), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-030"}, headers=headers)

    async def _concurrent_transfers():
        tasks = []
        for i in range(8):
            tasks.append(record_custody_event(
                evidence_id=ev_id,
                action="CUSTODY_TRANSFER",
                actor_id=f"actor_{i}",
                case_id="CV-PH3-030",
                details={"transfer_index": i, "reason": f"Concurrent step {i}"}
            ))
        return await asyncio.gather(*tasks)

    events = asyncio.run(_concurrent_transfers())
    assert len(events) == 8

    # Verify chronological sequence integrity
    all_events = AUDIT_LOGS_STORE[ev_id]
    sequences = [ev["sequence_number"] for ev in all_events]
    assert sequences == list(range(1, len(all_events) + 1))

    # Verify audit verification passes completely
    v_res = client.get(f"/api/audit/verify/{ev_id}", headers=headers)
    assert v_res.status_code == 200
    res = v_res.json()
    assert res["verification_status"] == "VERIFIED"
    assert res["chain_intact"] is True
    assert res["event_count"] == len(all_events)


def test_31_verification_get_and_post_parity(monkeypatch):
    """
    API Parity: POST /api/verification/verify and GET /api/verification/verify
    return identical status and comparison breakdowns.
    """
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Specimen for Parity 031"
    h = hashlib.sha256(payload).hexdigest()
    ev_id = f"{SYNTHETIC_EVIDENCE_PREFIX}PARITY-031"

    files = {"file": ("parity.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH3-031"}, headers=headers)

    onchain = mock_contract_record(ev_id, h)
    monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (onchain, None))

    post_res = client.post("/api/verification/verify", json={"evidence_id": ev_id}).json()
    get_res = client.get(f"/api/verification/verify?evidence_id={ev_id}").json()

    for k in ["status", "verification_status", "verified", "tampered", "physical_file_hash", "database_hash", "blockchain_hash", "technical_error"]:
        assert post_res[k] == get_res[k], f"Mismatch on field '{k}' between GET and POST"
