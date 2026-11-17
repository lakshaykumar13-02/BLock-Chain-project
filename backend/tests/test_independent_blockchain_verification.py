"""
ChainVault Phase 1 — Independent Blockchain Verification Test Suite
=====================================================================
Mandatory Automated Negative & Regression Tests:
1. Test 1: Original evidence (File == DB == Blockchain -> VERIFIED)
2. Test 2: Modified evidence file (File != Blockchain -> TAMPERED)
3. Test 3: MongoDB hash manipulation (DB != Blockchain, File == Blockchain -> INCONSISTENT)
           [PRIMARY ACCEPTANCE TEST FOR PHASE 1]
4. Test 4: Missing blockchain registration (DB exists, Chain missing -> INCONSISTENT / Fails closed)
5. Test 5: Incorrect evidence identifier (Unregistered ID -> NOT_FOUND)
6. Test 6: Blockchain unavailable (RPC offline simulation -> UNAVAILABLE / Fails closed)
7. Test 7: Missing evidence file (Physical file deleted -> TAMPERED / PHYSICAL_FILE_MISSING)
8. Test 8: GET endpoint & regression contracts (No hash mutation during verification)
"""

import io
import os
import urllib.error
import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.evidence import EVIDENCE_STORE
from app.services.blockchain import CHAIN_EVIDENCE_STORE

client = TestClient(app)


def get_test_auth_token(username="investigator1"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200
    return res.json()["access_token"]


@pytest.fixture(autouse=True)
def cleanup_synthetic_records():
    """Ensure all synthetic test evidence is cleaned up after each test."""
    synthetic_ids = [
        "EV-SYN-001", "EV-SYN-002", "EV-SYN-003",
        "EV-SYN-004", "EV-SYN-005", "EV-SYN-006",
        "EV-SYN-007", "EV-SYN-008"
    ]
    yield
    for ev_id in synthetic_ids:
        rec = EVIDENCE_STORE.pop(ev_id, None)
        if rec and rec.get("file_path") and os.path.exists(rec["file_path"]):
            try:
                os.remove(rec["file_path"])
            except OSError:
                pass
        CHAIN_EVIDENCE_STORE.pop(ev_id, None)


# -----------------------------------------------------------------------------
# TEST 1 — Original Evidence
# -----------------------------------------------------------------------------
def test_01_original_evidence_verified():
    """
    Test 1: Original evidence
    File, MongoDB record, and blockchain registration contain the identical hash.
    Expected: VERIFIED.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Authentic Untampered Digital Specimen 001"
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-001"
    files = {"file": ("specimen_001.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-001", "evidence_id": ev_id}

    # Upload evidence
    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    # Register on-chain
    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": expected_sha256, "case_id": "CV-SYN-001"},
        headers=headers
    )
    assert reg_res.status_code == 200

    # Verify tripartite integrity
    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()

    assert res["status"] == "success"
    assert res["verification_status"] == "VERIFIED"
    assert res["verified"] is True
    assert res["tampered"] is False
    assert res["file_status"] == "present"
    assert res["blockchain_verified"] is True
    assert res["technical_error"] is None

    # Check three individual hashes
    assert res["physical_file_hash"] == expected_sha256
    assert res["database_hash"] == expected_sha256
    assert res["blockchain_hash"] == expected_sha256

    # Check pairwise comparisons
    assert res["comparisons"]["file_vs_database"] is True
    assert res["comparisons"]["file_vs_blockchain"] is True
    assert res["comparisons"]["database_vs_blockchain"] is True
    assert res["file_vs_database"] is True
    assert res["file_vs_blockchain"] is True
    assert res["database_vs_blockchain"] is True


# -----------------------------------------------------------------------------
# TEST 2 — Modified Evidence File
# -----------------------------------------------------------------------------
def test_02_modified_evidence_file_tampered():
    """
    Test 2: Modified evidence file
    Modify a disposable test copy after registration while keeping the original
    blockchain registration and database record unchanged.
    Expected: The mismatch is detected and the result is TAMPERED.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Original Specimen 002 Before Tampering"
    original_sha256 = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-002"
    files = {"file": ("specimen_002.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-002", "evidence_id": ev_id}

    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": original_sha256, "case_id": "CV-SYN-002"},
        headers=headers
    )
    assert reg_res.status_code == 200

    # Tamper with the physical file on disk
    file_path = EVIDENCE_STORE[ev_id]["file_path"]
    with open(file_path, "wb") as f:
        f.write(b"CORRUPTED AND TAMPERED CONTENT BY THREAT ACTOR")

    fresh_file_sha256 = hashlib.sha256(b"CORRUPTED AND TAMPERED CONTENT BY THREAT ACTOR").hexdigest()

    # Verify tripartite integrity
    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()

    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "FILE_HASH_MISMATCH_TAMPERED"

    # Hashes must remain distinct
    assert res["physical_file_hash"] == fresh_file_sha256
    assert res["database_hash"] == original_sha256
    assert res["blockchain_hash"] == original_sha256

    # Comparison breakdown: file does NOT match blockchain or database
    assert res["comparisons"]["file_vs_blockchain"] is False
    assert res["comparisons"]["file_vs_database"] is False
    assert res["comparisons"]["database_vs_blockchain"] is True


# -----------------------------------------------------------------------------
# TEST 3 — MongoDB Hash Manipulation (PRIMARY ACCEPTANCE TEST FOR PHASE 1)
# -----------------------------------------------------------------------------
def test_03_mongodb_hash_manipulation_inconsistent():
    """
    Test 3: MongoDB hash manipulation (Primary Phase 1 Acceptance Test)
    Register synthetic evidence on the test blockchain, then change only the
    corresponding MongoDB hash to a different valid SHA-256 value.
    Keep the original evidence file and blockchain registration unchanged.

    Expected:
    - The MongoDB-versus-blockchain comparison fails.
    - The file-versus-blockchain comparison still reflects the actual file.
    - The result cannot be VERIFIED.
    - The result is INCONSISTENT.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Sacrosanct Forensic Evidence 003 Payload"
    authentic_sha256 = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-003"
    files = {"file": ("specimen_003.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-003", "evidence_id": ev_id}

    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": authentic_sha256, "case_id": "CV-SYN-003"},
        headers=headers
    )
    assert reg_res.status_code == 200

    # Manipulate ONLY the MongoDB stored hash
    manipulated_hash = hashlib.sha256(b"MALICIOUSLY_ALTERED_DATABASE_HASH_999").hexdigest()
    assert manipulated_hash != authentic_sha256
    EVIDENCE_STORE[ev_id]["file_hash"] = manipulated_hash

    # Execute verification
    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()

    # PRIMARY ACCEPTANCE ASSERTIONS:
    # 1. CANNOT be VERIFIED
    assert res["verified"] is False
    assert res["verification_status"] == "INCONSISTENT"
    assert res["technical_error"] == "DATABASE_HASH_MANIPULATED"

    # 2. Database vs Blockchain comparison fails
    assert res["comparisons"]["database_vs_blockchain"] is False
    assert res["database_vs_blockchain"] is False

    # 3. File vs Database comparison fails
    assert res["comparisons"]["file_vs_database"] is False
    assert res["file_vs_database"] is False

    # 4. File vs Blockchain comparison SUCCEEDS (actual physical file matches authentic chain!)
    assert res["comparisons"]["file_vs_blockchain"] is True
    assert res["file_vs_blockchain"] is True

    # 5. Hashes reported separately and un-overwritten
    assert res["physical_file_hash"] == authentic_sha256
    assert res["blockchain_hash"] == authentic_sha256
    assert res["database_hash"] == manipulated_hash

    # 6. Explanation clearly details database alteration
    assert "Database recorded hash does not match" in res["explanation"]
    assert "altered" in res["explanation"]


# -----------------------------------------------------------------------------
# TEST 4 — Missing Blockchain Registration
# -----------------------------------------------------------------------------
def test_04_missing_blockchain_registration_fails():
    """
    Test 4: Missing blockchain registration
    Use an evidence identifier that has no registration in the test contract.
    Expected: The system does not accept the MongoDB hash as blockchain proof.
              Result is INCONSISTENT with NOT_REGISTERED_ON_BLOCKCHAIN.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Unanchored Evidence Specimen 004"
    sha256_hash = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-004"
    files = {"file": ("specimen_004.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-004", "evidence_id": ev_id}

    # Upload only (do not register on blockchain)
    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    # Ensure explicitly absent from chain store and contract
    CHAIN_EVIDENCE_STORE.pop(ev_id, None)

    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()

    assert res["verified"] is False
    assert res["verification_status"] == "INCONSISTENT"
    assert res["technical_error"] == "NOT_REGISTERED_ON_BLOCKCHAIN"
    assert res["blockchain_verified"] is False
    assert res["blockchain_hash"] is None
    assert "has not been anchored" in res["explanation"]


# -----------------------------------------------------------------------------
# TEST 5 — Incorrect Evidence Identifier
# -----------------------------------------------------------------------------
def test_05_incorrect_evidence_id_not_found():
    """
    Test 5: Incorrect evidence identifier
    Request an identifier that does not match the intended blockchain record.
    Expected: No unrelated evidence registration is accepted as proof; NOT_FOUND returned.
    """
    verify_res = client.post(
        "/api/verification/verify",
        json={"evidence_id": "EV-SYN-NONEXISTENT-9999"}
    )
    assert verify_res.status_code == 200
    res = verify_res.json()

    assert res["verified"] is False
    assert res["verification_status"] == "NOT_FOUND"
    assert res["technical_error"] == "RECORD_NOT_FOUND"
    assert res["blockchain_hash"] is None
    assert res["database_hash"] is None
    assert res["physical_file_hash"] is None


# -----------------------------------------------------------------------------
# TEST 6 — Blockchain Unavailable (Fails Closed)
# -----------------------------------------------------------------------------
def test_06_blockchain_unavailable_fails_closed(monkeypatch):
    """
    Test 6: Blockchain unavailable
    Simulate a failed RPC connection using existing test infrastructure.
    Expected: Verification fails closed, returns UNAVAILABLE, and never reports VERIFIED.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Evidence Tested During Network Outage 006"
    sha256_hash = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-006"
    files = {"file": ("specimen_006.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-006", "evidence_id": ev_id}

    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    # Simulate RPC failure by monkeypatching query_contract_evidence
    def mock_query_contract_failure(evidence_id):
        return None, "RPC_UNAVAILABLE"

    monkeypatch.setattr(
        "app.services.blockchain.query_contract_evidence",
        mock_query_contract_failure
    )

    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()

    assert res["verified"] is False
    assert res["tampered"] is False  # Offline infrastructure is not false tampering
    assert res["verification_status"] == "UNAVAILABLE"
    assert res["technical_error"] == "BLOCKCHAIN_RPC_UNAVAILABLE"
    assert res["blockchain_status"] == "unavailable"
    assert "offline or unreachable" in res["explanation"]


# -----------------------------------------------------------------------------
# TEST 7 — Missing Evidence File
# -----------------------------------------------------------------------------
def test_07_missing_evidence_file_fails():
    """
    Test 7: Missing evidence file
    Keep the relevant test metadata but remove the disposable test file.
    Expected: The missing file is reported explicitly; no previous hash is
              substituted for a fresh file hash.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Disposable Evidence File Specimen 007"
    sha256_hash = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-007"
    files = {"file": ("specimen_007.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-007", "evidence_id": ev_id}

    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": sha256_hash, "case_id": "CV-SYN-007"},
        headers=headers
    )
    assert reg_res.status_code == 200

    # Delete the physical file from disk
    file_path = EVIDENCE_STORE[ev_id]["file_path"]
    if os.path.exists(file_path):
        os.remove(file_path)

    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()

    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["file_status"] == "missing"
    assert res["physical_file_hash"] is None  # Never substitute a previous hash!
    assert res["technical_error"] == "PHYSICAL_FILE_MISSING"
    assert "missing from disk" in res["explanation"]


# -----------------------------------------------------------------------------
# TEST 8 — API Regression & Contract Immutability
# -----------------------------------------------------------------------------
def test_08_get_endpoint_and_regression_contracts():
    """
    Test 8: Regression
    1. Validates GET /api/verification/verify?evidence_id=... returns identical output.
    2. Validates external check_hash comparator flags mismatches.
    3. Confirms that verification queries NEVER mutate stored database or chain records.
    """
    token = get_test_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    payload = b"Immutable Regression Specimen 008"
    sha256_hash = hashlib.sha256(payload).hexdigest()

    ev_id = "EV-SYN-008"
    files = {"file": ("specimen_008.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-SYN-008", "evidence_id": ev_id}

    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": sha256_hash, "case_id": "CV-SYN-008"},
        headers=headers
    )
    assert reg_res.status_code == 200

    # 1. GET endpoint verification
    get_res = client.get(f"/api/verification/verify?evidence_id={ev_id}")
    assert get_res.status_code == 200
    res_data = get_res.json()
    assert res_data["verification_status"] == "VERIFIED"
    assert res_data["verified"] is True

    # 2. External comparator check
    bad_check_res = client.post(
        "/api/verification/verify",
        json={"evidence_id": ev_id, "check_hash": "deadbeef" * 8}
    )
    assert bad_check_res.status_code == 200
    bad_data = bad_check_res.json()
    assert bad_data["verified"] is False
    assert bad_data["tampered"] is True
    assert bad_data["technical_error"] == "COMPARATOR_MISMATCH"

    # 3. Check records remain unmutated
    assert EVIDENCE_STORE[ev_id]["file_hash"] == sha256_hash
    assert EVIDENCE_STORE[ev_id]["blockchain_registered"] is True
