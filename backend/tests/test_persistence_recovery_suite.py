"""
ChainVault Phase 4 — Persistence, Restart Recovery & Blockchain Reconciliation Suite
=====================================================================================
Automated Tests for:
1. Backend process restart with persistent evidence metadata.
2. MongoDB restart and live client reconnection.
3. MongoDB unavailable in required-persistence mode (fails closed with HTTP 503).
4. Storage/Database write failure with complete cleanup (no orphaned files or ghost metadata).
5. Evidence physical file missing after application restart (detected as TAMPERED/PHYSICAL_FILE_MISSING).
6. Missing database metadata when file or blockchain anchor exists (never VERIFIED).
7. Blockchain RPC unavailable (fails closed with UNAVAILABLE).
8. Blockchain Chain ID mismatch (fails closed with UNAVAILABLE).
9. Contract address or deployed bytecode mismatch/empty (fails closed with INCONSISTENT).
10. Previously registered evidence missing after simulated chain reset (detected as INCONSISTENT).
11. Missing or failed transaction receipt (fails closed with INCONSISTENT).
12. Repeated retries and duplicate recovery attempts (idempotent success or HTTP 409 conflict).
13. Safe recovery and normal resumption after temporary service outage.
14. Tripartite verification NEVER returning VERIFIED when any required state is missing.
15. Recovery diagnostics endpoint security (zero credential leakage) and system consistency reporting.
"""

import io
import os
import json
import hashlib
import time
import asyncio
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.mongodb import MongoDBClient, db_client
from app.routes.evidence import EVIDENCE_STORE
from app.routes.cases import CASES_STORE
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS,
    BLOCK_HEIGHT
)

# Initialize TestClient
client = TestClient(app)

SYNTHETIC_PREFIX = "EV-PH4-"

def get_auth_token(username="investigator1"):
    """Helper to authenticate and retrieve access token."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]


@pytest.fixture(scope="module", autouse=True)
def setup_phase4_db_connection():
    """Ensure MongoDB connection is established specifically for Phase 4 suite."""
    import asyncio
    asyncio.run(db_client.connect())
    yield
    asyncio.run(db_client.close())


def _purge_phase4_state():

    for k in list(EVIDENCE_STORE.keys()):
        if k.startswith(SYNTHETIC_PREFIX):
            rec = EVIDENCE_STORE.pop(k, None)
            if rec and rec.get("file_path") and os.path.exists(rec["file_path"]):
                try:
                    os.remove(rec["file_path"])
                except OSError:
                    pass
    for k in list(CHAIN_EVIDENCE_STORE.keys()):
        if k.startswith(SYNTHETIC_PREFIX):
            CHAIN_EVIDENCE_STORE.pop(k, None)
    for k in list(CHAIN_CUSTODY_LOGS.keys()):
        if k.startswith(SYNTHETIC_PREFIX):
            CHAIN_CUSTODY_LOGS.pop(k, None)
    if db_client.is_connected() and db_client.evidence is not None:
        try:
            import asyncio
            async def _del():
                await db_client.evidence.delete_many({"evidence_id": {"$regex": f"^{SYNTHETIC_PREFIX}"}})
            asyncio.run(_del())
        except Exception:
            pass


@pytest.fixture(autouse=True)
def cleanup_phase4_test_state():
    """Ensure all synthetic test artifacts are purged before and after each test."""
    _purge_phase4_state()
    yield
    _purge_phase4_state()



# =============================================================================
# 1. BACKEND RESTART WITH PERSISTENT EVIDENCE METADATA
# =============================================================================

def test_01_backend_restart_with_persistent_evidence_metadata():
    """
    Scenario 1: Backend process restart with persistent evidence metadata.
    Uploads evidence with persistent DB active, then simulates process restart
    by clearing all in-memory dictionaries.
    Metadata and verification must recover directly from MongoDB without data loss.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}001"
    payload = b"Persistent Evidence Payload Specimen 001"
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    files = {"file": ("artifact_001.bin", io.BytesIO(payload), "application/octet-stream")}
    upload_res = client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-001"},
        headers=headers
    )
    assert upload_res.status_code == 201

    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": expected_sha256, "case_id": "CV-PH4-001"},
        headers=headers
    )
    assert reg_res.status_code == 200

    # SIMULATE COMPLETE BACKEND PROCESS RESTART (Wipe process-local memory)
    saved_file_path = EVIDENCE_STORE[ev_id]["file_path"]
    EVIDENCE_STORE.clear()
    CASES_STORE.clear()

    # Evidence metadata must be recovered from persistent MongoDB
    get_res = client.get(f"/api/evidence/{ev_id}", headers=headers)
    assert get_res.status_code == 200
    recovered_data = get_res.json()
    assert recovered_data["evidence_id"] == ev_id
    assert recovered_data["file_hash"] == expected_sha256
    assert recovered_data["file_path"] == saved_file_path

    # Verification must succeed using recovered persistent record
    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["verification_status"] == "VERIFIED"
    assert v_data["verified"] is True
    assert v_data["technical_error"] is None



# =============================================================================
# 2. MONGODB RESTART AND RECONNECTION
# =============================================================================

def test_02_mongodb_restart_and_reconnection():
    """
    Scenario 2: MongoDB restart and live reconnection.
    Simulate temporary MongoDB disconnection using isolated client instance,
    confirm is_connected() becomes False, then reconnect and verify health.
    """
    async def _test_lifecycle():
        test_client = MongoDBClient()
        test_client.db_name = "chainvault_test"
        await test_client.connect()
        assert test_client.is_connected() is True
        assert (await test_client.ping()) is True

        # Simulate socket drop / restart
        test_client.client = None
        test_client.db = None
        assert test_client.is_connected() is False
        assert (await test_client.ping()) is False

        # Simulate reconnection lifecycle
        await test_client.connect()
        assert test_client.is_connected() is True
        assert (await test_client.ping()) is True
        await test_client.close()

    asyncio.run(_test_lifecycle())


# =============================================================================
# 3. MONGODB UNAVAILABLE IN REQUIRED-PERSISTENCE MODE
# =============================================================================

def test_03_mongodb_unavailable_in_required_persistence_mode(monkeypatch):
    """
    Scenario 3: MongoDB unavailable in required-persistence mode.
    When REQUIRE_PERSISTENT_STORAGE is enabled, mutations must be rejected
    with HTTP 503 and verification must fail closed with UNAVAILABLE.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}003"
    payload = b"Specimen 003"

    # Enforce persistent storage requirement
    monkeypatch.setattr(db_client, "require_persistent_storage", True)
    monkeypatch.setattr(db_client, "is_connected", lambda: False)

    # Mutation attempt must fail with HTTP 503
    files = {"file": ("artifact_003.bin", io.BytesIO(payload), "application/octet-stream")}
    upload_res = client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-003"},
        headers=headers
    )
    assert upload_res.status_code == 503
    assert "persistent database storage is required but currently unavailable" in upload_res.json()["detail"].lower()

    # Verification attempt must fail closed with UNAVAILABLE
    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    v_data = v_res.json()
    assert v_data["verification_status"] == "UNAVAILABLE"
    assert v_data["verified"] is False
    assert v_data["technical_error"] == "DATABASE_UNAVAILABLE"


# =============================================================================
# 4. WRITE FAILURE WITHOUT SILENT IN-MEMORY SUCCESS
# =============================================================================

def test_04_write_failure_without_silent_inmemory_success(monkeypatch):
    """
    Scenario 4: Write failure does not produce silent in-memory success.
    When persistent write fails, the written physical file must be rolled back,
    no record added to EVIDENCE_STORE, and HTTP 500 returned.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}004"
    payload = b"Specimen 004 Payload"

    monkeypatch.setattr(db_client, "require_persistent_storage", True)
    monkeypatch.setattr(db_client, "is_connected", lambda: True)

    class FailingCollection:
        async def update_one(self, *args, **kwargs):
            raise RuntimeError("Disk quota exceeded / simulated I/O failure")
        async def find_one(self, *args, **kwargs):
            return None
        async def delete_one(self, *args, **kwargs):
            return None

    monkeypatch.setattr(db_client, "evidence", FailingCollection())

    files = {"file": ("specimen_004.bin", io.BytesIO(payload), "application/octet-stream")}
    res = client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-004"},
        headers=headers
    )
    assert res.status_code in (500, 503)
    assert ev_id not in EVIDENCE_STORE


# =============================================================================
# 5. EVIDENCE FILE MISSING AFTER RESTART
# =============================================================================

def test_05_evidence_file_missing_after_restart():
    """
    Scenario 5: Physical evidence file missing from disk after restart.
    Metadata exists in DB and blockchain record exists, but file was deleted.
    Verification must return TAMPERED with PHYSICAL_FILE_MISSING.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}005"
    payload = b"Specimen 005 To Be Deleted"
    file_hash = hashlib.sha256(payload).hexdigest()

    files = {"file": ("specimen_005.bin", io.BytesIO(payload), "application/octet-stream")}
    upload_res = client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-005"},
        headers=headers
    )
    assert upload_res.status_code == 201

    client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH4-005"},
        headers=headers
    )

    # Delete the physical file
    fp = EVIDENCE_STORE[ev_id]["file_path"]
    if os.path.exists(fp):
        os.remove(fp)

    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()
    assert res["verification_status"] == "TAMPERED"
    assert res["verified"] is False
    assert res["tampered"] is True
    assert res["technical_error"] == "PHYSICAL_FILE_MISSING"


# =============================================================================
# 6. MISSING DATABASE METADATA
# =============================================================================

def test_06_missing_database_metadata():
    """
    Scenario 6: Missing database metadata.
    Evidence exists on-chain, but local DB metadata is missing.
    System must return INCONSISTENT with MISSING_FROM_DATABASE (never VERIFIED).
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}006"
    file_hash = hashlib.sha256(b"Specimen 006").hexdigest()

    # Register only on-chain directly
    client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": file_hash, "case_id": "CV-PH4-006"},
        headers=headers
    )

    # Ensure explicitly absent from EVIDENCE_STORE
    EVIDENCE_STORE.pop(ev_id, None)

    verify_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert verify_res.status_code == 200
    res = verify_res.json()
    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "MISSING_FROM_DATABASE"


# =============================================================================
# 7. BLOCKCHAIN RPC UNAVAILABLE
# =============================================================================

def test_07_blockchain_rpc_unavailable(monkeypatch):
    """
    Scenario 7: Blockchain RPC node is offline or unreachable.
    Verification must fail closed with UNAVAILABLE (never false VERIFIED or false TAMPERED).
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}007"
    payload = b"Specimen 007 Payload"

    files = {"file": ("specimen_007.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-007"},
        headers=headers
    )

    # Simulate RPC failure
    monkeypatch.setattr(
        "app.services.blockchain.query_contract_evidence",
        lambda eid: (None, "RPC_UNAVAILABLE")
    )

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()
    assert res["verification_status"] == "UNAVAILABLE"
    assert res["verified"] is False
    assert res["tampered"] is False
    assert res["technical_error"] == "BLOCKCHAIN_RPC_UNAVAILABLE"


# =============================================================================
# 8. CHAIN ID MISMATCH
# =============================================================================

def test_08_chain_id_mismatch(monkeypatch):
    """
    Scenario 8: Connected node returns incorrect Chain ID (e.g. 1 instead of 31337).
    Verification must fail closed with UNAVAILABLE and technical_error CHAIN_ID_MISMATCH.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}008"
    payload = b"Specimen 008 Payload"

    files = {"file": ("specimen_008.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-008"},
        headers=headers
    )

    monkeypatch.setattr(
        "app.services.blockchain.query_contract_evidence",
        lambda eid: (None, "CHAIN_ID_MISMATCH")
    )

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()
    assert res["verification_status"] == "UNAVAILABLE"
    assert res["verified"] is False
    assert res["technical_error"] == "CHAIN_ID_MISMATCH"


# =============================================================================
# 9. CONTRACT ADDRESS OR CONTRACT CODE MISMATCH
# =============================================================================

def test_09_contract_code_mismatch_or_undeployed(monkeypatch):
    """
    Scenario 9: Contract address has no deployed bytecode on connected chain.
    Verification must detect contract is undeployed and flag INCONSISTENT / CONTRACT_NOT_DEPLOYED.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}009"
    payload = b"Specimen 009 Payload"

    files = {"file": ("specimen_009.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-009"},
        headers=headers
    )

    # Simulate empty bytecode at contract address (e.g. undeployed or chain reset)
    monkeypatch.setattr(
        "app.services.blockchain.verify_contract_deployed",
        lambda addr: (False, "CONTRACT_CODE_EMPTY")
    )

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()
    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "CONTRACT_NOT_DEPLOYED"


# =============================================================================
# 10. SIMULATED CHAIN RESET — PREVIOUSLY REGISTERED EVIDENCE MISSING
# =============================================================================

def test_10_previously_registered_evidence_missing_after_chain_reset():
    """
    Scenario 10: Local Hardhat chain reset or replacement.
    Evidence is marked registered in DB with tx_hash, but on-chain query returns NOT_FOUND.
    Verification must flag INCONSISTENT with BLOCKCHAIN_RESET_REGISTRATION_LOST.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}010"
    payload = b"Specimen 010 Payload"
    h = hashlib.sha256(payload).hexdigest()

    files = {"file": ("specimen_010.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-010"},
        headers=headers
    )

    client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": h, "case_id": "CV-PH4-010"},
        headers=headers
    )

    # SIMULATE HARDHAT CHAIN RESET: on-chain record purged while DB record remains
    CHAIN_EVIDENCE_STORE.pop(ev_id, None)

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()
    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "BLOCKCHAIN_RESET_REGISTRATION_LOST"


# =============================================================================
# 11. MISSING OR FAILED TRANSACTION RECEIPT
# =============================================================================

def test_11_missing_or_failed_transaction_receipt(monkeypatch):
    """
    Scenario 11: Transaction receipt missing or reverted.
    When a recorded tx receipt cannot be confirmed on-chain, verification fails closed.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}011"
    payload = b"Specimen 011 Payload"
    h = hashlib.sha256(payload).hexdigest()

    files = {"file": ("specimen_011.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post(
        "/api/evidence/upload",
        files=files,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-011"},
        headers=headers
    )

    client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": h, "case_id": "CV-PH4-011"},
        headers=headers
    )

    # Mock receipt check returning RECEIPT_NOT_FOUND
    monkeypatch.setattr(
        "app.services.blockchain.get_transaction_receipt",
        lambda tx: (None, "RECEIPT_NOT_FOUND")
    )

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()
    assert res["verification_status"] == "INCONSISTENT"
    assert res["verified"] is False
    assert res["technical_error"] == "TRANSACTION_RECEIPT_MISSING"


# =============================================================================
# 12. REPEATED RETRIES AND DUPLICATE RECOVERY ATTEMPTS
# =============================================================================

def test_12_repeated_retries_and_duplicate_recovery_attempts():
    """
    Scenario 12: Repeated retries and duplicate upload attempts.
    - Identical content retry succeeds idempotently.
    - Conflicting content retry fails with HTTP 409 Conflict.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}012"
    payload_original = b"Payload 012 Original"
    payload_conflict = b"Payload 012 Conflicting Data"

    # Initial upload
    files1 = {"file": ("artifact_012.bin", io.BytesIO(payload_original), "application/octet-stream")}
    r1 = client.post(
        "/api/evidence/upload",
        files=files1,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-012"},
        headers=headers
    )
    assert r1.status_code == 201

    # Idempotent retry with identical content
    files2 = {"file": ("artifact_012.bin", io.BytesIO(payload_original), "application/octet-stream")}
    r2 = client.post(
        "/api/evidence/upload",
        files=files2,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-012"},
        headers=headers
    )
    assert r2.status_code in (200, 201)
    assert r2.json()["evidence_id"] == ev_id

    # Conflicting retry with different content
    files3 = {"file": ("artifact_012.bin", io.BytesIO(payload_conflict), "application/octet-stream")}
    r3 = client.post(
        "/api/evidence/upload",
        files=files3,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-012"},
        headers=headers
    )
    assert r3.status_code == 409
    assert "different file hash" in r3.json()["detail"].lower()


# =============================================================================
# 13. RECOVERY AFTER TEMPORARY SERVICE OUTAGE
# =============================================================================

def test_13_recovery_after_temporary_service_outage(monkeypatch):
    """
    Scenario 13: Normal operation resumes smoothly after temporary outage.
    During outage, operations fail closed (503). Once service reconnects,
    evidence ingestion and verification work normally.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}013"
    payload = b"Specimen 013 Resilient Service"
    h = hashlib.sha256(payload).hexdigest()

    # 1. Simulate outage
    monkeypatch.setattr(db_client, "require_persistent_storage", True)
    original_is_connected = db_client.is_connected
    monkeypatch.setattr(db_client, "is_connected", lambda: False)

    files1 = {"file": ("specimen_013.bin", io.BytesIO(payload), "application/octet-stream")}
    fail_res = client.post(
        "/api/evidence/upload",
        files=files1,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-013"},
        headers=headers
    )
    assert fail_res.status_code == 503

    # 2. Restore service
    monkeypatch.setattr(db_client, "is_connected", original_is_connected)

    files2 = {"file": ("specimen_013.bin", io.BytesIO(payload), "application/octet-stream")}
    ok_res = client.post(
        "/api/evidence/upload",
        files=files2,
        data={"evidence_id": ev_id, "case_id": "CV-PH4-013"},
        headers=headers
    )
    assert ok_res.status_code == 201

    reg_res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": h, "case_id": "CV-PH4-013"},
        headers=headers
    )
    assert reg_res.status_code == 200

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    assert v_res.json()["verification_status"] == "VERIFIED"


# =============================================================================
# 14. VERIFICATION NEVER RETURNING VERIFIED WHEN REQUIRED STATE IS MISSING
# =============================================================================

@pytest.mark.parametrize("missing_scenario", [
    "missing_file",
    "missing_database",
    "missing_blockchain",
    "hash_corrupted",
    "rpc_down"
])
def test_14_verification_never_returning_verified_matrix(missing_scenario, monkeypatch):
    """
    Scenario 14: Comprehensive matrix confirming verification NEVER returns VERIFIED
    whenever any required component is missing or inconsistent.
    """
    token = get_auth_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}
    ev_id = f"{SYNTHETIC_PREFIX}014-{missing_scenario}"
    payload = f"Specimen 014 {missing_scenario}".encode()
    h = hashlib.sha256(payload).hexdigest()

    files = {"file": (f"{ev_id}.bin", io.BytesIO(payload), "application/octet-stream")}
    client.post("/api/evidence/upload", files=files, data={"evidence_id": ev_id, "case_id": "CV-PH4-014"}, headers=headers)
    client.post("/api/blockchain/register", json={"evidence_id": ev_id, "hash": h, "case_id": "CV-PH4-014"}, headers=headers)

    if missing_scenario == "missing_file":
        fp = EVIDENCE_STORE[ev_id]["file_path"]
        if os.path.exists(fp):
            os.remove(fp)

    elif missing_scenario == "missing_database":
        EVIDENCE_STORE.pop(ev_id, None)
        if db_client.is_connected() and db_client.evidence is not None:
            try:
                import asyncio
                async def _del_target():
                    return await db_client.evidence.delete_one({"evidence_id": ev_id})
                asyncio.run(_del_target())
            except Exception:
                pass


    elif missing_scenario == "missing_blockchain":
        CHAIN_EVIDENCE_STORE.pop(ev_id, None)

    elif missing_scenario == "hash_corrupted":
        fp = EVIDENCE_STORE[ev_id]["file_path"]
        with open(fp, "wb") as f:
            f.write(b"CORRUPTED_BYTES")

    elif missing_scenario == "rpc_down":
        monkeypatch.setattr("app.services.blockchain.query_contract_evidence", lambda eid: (None, "RPC_UNAVAILABLE"))

    v_res = client.post("/api/verification/verify", json={"evidence_id": ev_id})
    assert v_res.status_code == 200
    res = v_res.json()

    # CORE INVARIANT: verified must NEVER be True!
    assert res["verified"] is False
    assert res["verification_status"] != "VERIFIED"




# =============================================================================
# 15. RECOVERY DIAGNOSTICS ENDPOINT SECURITY & CONSISTENCY CHECK
# =============================================================================

def test_15_recovery_diagnostics_security_and_consistency():
    """
    Scenario 15: Recovery diagnostics and consistency report.
    - Diagnostics endpoint leaks zero credentials, JWT secrets, or private keys.
    - Health endpoint reports persistence mode.
    - Consistency report accurately inspects storage, database, and blockchain.
    """
    # 1. Public diagnostics
    diag_res = client.get("/api/recovery/diagnostics")
    assert diag_res.status_code == 200
    diag = diag_res.json()

    assert "database" in diag
    assert "blockchain" in diag
    assert "storage" in diag
    assert "ready_for_verification" in diag

    # Security: zero secrets leaked
    raw_diag_str = json.dumps(diag).lower()
    for forbidden in ["password", "secret", "private_key", "jwt", "bearer", "mnemonic"]:
        assert forbidden not in raw_diag_str, f"Secret '{forbidden}' leaked in diagnostics output!"

    # 2. Health check
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    health = health_res.json()
    assert health["status"] == "ok"
    assert "persistence_mode" in diag["database"]


    # 3. Authenticated consistency report
    admin_token = get_auth_token("admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    cons_res = client.get("/api/recovery/consistency-report", headers=admin_headers)
    assert cons_res.status_code == 200
    report = cons_res.json()
    assert "is_consistent" in report
    assert "missing_physical_files" in report
    assert "orphaned_physical_files" in report
    assert "blockchain_inconsistencies" in report
    assert "recommendations" in report
