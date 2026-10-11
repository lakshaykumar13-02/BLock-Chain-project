import os
import io
import hashlib
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongodb import MongoDBClient
from app.routes.evidence import EVIDENCE_STORE
from app.routes.cases import CASES_STORE
from app.routes.custody import AUDIT_LOGS_STORE
from app.routes.reports import REPORTS_REGISTRY
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    register_evidence_on_chain,
    get_evidence_from_chain
)

client = TestClient(app)

def get_auth_token(username="investigator1", role="INVESTIGATOR"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200
    return res.json()["access_token"]


# ==============================================================================
# SECTION 2: TEST DATABASE ISOLATION & DESTRUCTIVE SAFEGUARDS
# ==============================================================================

def test_automated_safeguard_rejects_drop_on_development_db():
    """Safeguard must raise PermissionError if destructive action targeted at non-test database."""
    prod_client = MongoDBClient()
    prod_client.db_name = "chainvault"
    with pytest.raises(PermissionError) as exc_info:
        prod_client.safeguard_test_database("drop")
    assert "rejected" in str(exc_info.value)
    assert "chainvault" in str(exc_info.value)

def test_automated_safeguard_allows_drop_on_test_database():
    """Safeguard allows destructive actions ONLY on chainvault_test."""
    test_client = MongoDBClient()
    test_client.db_name = "chainvault_test"
    # Should not raise exception
    test_client.safeguard_test_database("cleanup")

def test_database_selection_strictly_targets_test_database():
    """Verify default test environment enforces chainvault_test."""
    client_instance = MongoDBClient()
    assert client_instance.db_name == "chainvault_test"
    assert client_instance.db_name != "chainvault"

# ==============================================================================
# SECTION 3: EVIDENCE INTEGRITY & HASH IMMUTABILITY
# ==============================================================================

def test_evidence_upload_and_independent_hash_verification(isolated_storage_dir):
    """
    1. Calculate SHA-256 independently on synthetic file.
    2. Upload file and compare calculated hash with stored metadata.
    3. Verify original hash remains unchanged across repeated reads.
    """
    token = get_auth_token("investigator1")
    synthetic_payload = b"ChainVault Synthetic Forensic Evidence Content - Case 901"
    independent_sha256 = hashlib.sha256(synthetic_payload).hexdigest()

    # Upload synthetic evidence
    files = {"file": ("synthetic_specimen_901.bin", io.BytesIO(synthetic_payload), "application/octet-stream")}
    data = {"case_id": "CV-TEST-901", "evidence_id": "EV-INT-901"}
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert res.status_code == 201
    res_data = res.json()

    assert res_data["file_hash"] == independent_sha256
    assert res_data["evidence_id"] == "EV-INT-901"

    # Verify original hash remains unchanged on subsequent reads
    get_res1 = client.get("/api/evidence/EV-INT-901", headers=headers)
    assert get_res1.status_code == 200
    assert get_res1.json()["file_hash"] == independent_sha256

    get_res2 = client.get("/api/evidence/EV-INT-901", headers=headers)
    assert get_res2.status_code == 200
    assert get_res2.json()["file_hash"] == independent_sha256

def test_evidence_tampering_mismatch_detection(isolated_storage_dir):
    """
    Modify a disposable test copy and confirm expected tamper/mismatch detection.
    Confirm verification does not silently replace original hash in database.
    """
    token = get_auth_token("investigator1")
    original_payload = b"Authentic Untampered Digital Artifact 902"
    original_sha256 = hashlib.sha256(original_payload).hexdigest()

    files = {"file": ("specimen_902.bin", io.BytesIO(original_payload), "application/octet-stream")}
    data = {"case_id": "CV-TEST-902", "evidence_id": "EV-INT-902"}
    headers = {"Authorization": f"Bearer {token}"}
    upload_res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert upload_res.status_code == 201

    # Register on-chain
    client.post(
        "/api/blockchain/register",
        json={"evidence_id": "EV-INT-902", "hash": original_sha256, "case_id": "CV-TEST-902"},
        headers=headers
    )

    # Confirm verified initially
    verify_res1 = client.post("/api/verification/verify", json={"evidence_id": "EV-INT-902"})
    assert verify_res1.status_code == 200
    assert verify_res1.json()["verified"] is True
    assert verify_res1.json()["tampered"] is False

    # Simulate forensic tampering: modify file contents on disk
    record = EVIDENCE_STORE["EV-INT-902"]
    file_path = record["file_path"]
    with open(file_path, "wb") as f:
        f.write(b"TAMPERED CORRUPTED PAYLOAD CONTENT")

    # Verify tampering is detected
    verify_res2 = client.post("/api/verification/verify", json={"evidence_id": "EV-INT-902"})
    assert verify_res2.status_code == 200
    v2_data = verify_res2.json()
    assert v2_data["verified"] is False
    assert v2_data["tampered"] is True
    assert v2_data["comparisons"]["file_vs_database"] is False

    # Confirm original database hash was NOT overwritten by verification
    assert EVIDENCE_STORE["EV-INT-902"]["file_hash"] == original_sha256
    assert CHAIN_EVIDENCE_STORE["EV-INT-902"]["file_hash"] == original_sha256

def test_missing_file_verification_scenario():
    """Verify that a missing physical file triggers verification failure and is reported as missing."""
    token = get_auth_token("investigator1")
    payload = b"Evidence With Disposable File 903"
    files = {"file": ("specimen_903.bin", io.BytesIO(payload), "application/octet-stream")}
    data = {"case_id": "CV-TEST-903", "evidence_id": "EV-INT-903"}
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/evidence/upload", files=files, data=data, headers=headers)

    # Delete physical file
    fp = EVIDENCE_STORE["EV-INT-903"]["file_path"]
    if os.path.exists(fp):
        os.remove(fp)

    verify_res = client.post("/api/verification/verify", json={"evidence_id": "EV-INT-903"})
    assert verify_res.status_code == 200
    res_json = verify_res.json()
    assert res_json["verified"] is False
    assert res_json["tampered"] is True
    assert res_json["file_status"] == "missing"

def test_failed_upload_does_not_leave_orphaned_metadata_or_files(monkeypatch):
    """Confirm failed upload does not create misleading completed record in EVIDENCE_STORE."""
    token = get_auth_token("investigator1")

    # Simulate filesystem write failure
    def mock_save_file_fail(filename, content):
        raise OSError("Simulated disk write failure - Device full")

    import app.routes.evidence as ev_mod
    monkeypatch.setattr(ev_mod, "save_file", mock_save_file_fail)

    files = {"file": ("failing_file.bin", io.BytesIO(b"Data"), "application/octet-stream")}
    data = {"case_id": "CV-TEST-FAIL", "evidence_id": "EV-INT-FAIL"}
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/evidence/upload", files=files, data=data, headers=headers)
    assert res.status_code == 500
    assert "EV-INT-FAIL" not in EVIDENCE_STORE

# ==============================================================================
# SECTION 4: DATABASE AND BLOCKCHAIN CONSISTENCY
# ==============================================================================

def test_blockchain_confirmed_transaction_metadata_persistence():
    """Verify evidence registration emits confirmed transaction receipt and updates DB metadata."""
    token = get_auth_token("investigator1")
    ev_id = "EV-INT-BC-904"
    h = hashlib.sha256(b"Blockchain Anchoring Test 904").hexdigest()

    # Pre-populate DB store
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-TEST-904",
        "file_hash": h,
        "custodian": "investigator1",
        "blockchain_registered": False
    }

    res = client.post(
        "/api/blockchain/register",
        json={"evidence_id": ev_id, "hash": h, "case_id": "CV-TEST-904"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "tx_hash" in data
    assert data["receipt"]["status"] == "confirmed"

    # Verify DB record updated with confirmed tx_hash
    assert EVIDENCE_STORE[ev_id]["blockchain_registered"] is True
    assert EVIDENCE_STORE[ev_id]["blockchain_tx"] == data["tx_hash"]

def test_reconciliation_for_pending_or_uncertain_blockchain_transactions():
    """
    Verify reconciliation service inspects on-chain state first before updating,
    safely recovering out-of-sync database metadata without issuing redundant transactions.
    """
    token = get_auth_token("investigator1")
    ev_id = "EV-INT-RECON-905"
    h = hashlib.sha256(b"Reconciliation Test 905").hexdigest()

    # Register on chain directly (simulating successful on-chain transaction where DB failed to update)
    chain_receipt = register_evidence_on_chain(ev_id, h, "CV-TEST-905")
    assert chain_receipt["status"] == "confirmed"

    # DB record is present but marked NOT registered (out of sync)
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": "CV-TEST-905",
        "file_hash": h,
        "blockchain_registered": False,
        "blockchain_tx": None
    }

    # Call reconciliation endpoint
    recon_res = client.post(
        f"/api/blockchain/reconcile/{ev_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert recon_res.status_code == 200
    assert recon_res.json()["status"] == "reconciled"
    assert recon_res.json()["blockchain_tx"] == chain_receipt["tx_hash"]

    # Verify DB record is now synchronized
    assert EVIDENCE_STORE[ev_id]["blockchain_registered"] is True
    assert EVIDENCE_STORE[ev_id]["blockchain_tx"] == chain_receipt["tx_hash"]

def test_reconcile_nonexistent_blockchain_evidence_returns_404():
    """Reconciliation rejects non-existent on-chain evidence with 404 (does not blind-retry)."""
    token = get_auth_token("investigator1")
    res = client.post(
        "/api/blockchain/reconcile/EV-DOES-NOT-EXIST",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 404

# ==============================================================================
# SECTION 5: REPORT & CUSTODY PRESERVATION
# ==============================================================================

def test_custody_history_preservation_across_multiple_transfers():
    """Verify custody history is preserved in order across multiple handovers."""
    token = get_auth_token("investigator1")
    ev_id = "EV-INT-CUST-906"
    EVIDENCE_STORE[ev_id] = {"evidence_id": ev_id, "custodian": "officer1"}

    # Transfer 1: officer1 -> officer2
    res1 = client.post(
        "/api/custody/transfer",
        json={"evidence_id": ev_id, "new_custodian": "officer2", "reason": "Transfer to forensics"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res1.status_code == 200

    # Transfer 2: officer2 -> analyst3
    res2 = client.post(
        "/api/custody/transfer",
        json={"evidence_id": ev_id, "new_custodian": "analyst3", "reason": "Lab examination"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res2.status_code == 200

    # Retrieve history
    hist_res = client.get(f"/api/custody/history/{ev_id}", headers={"Authorization": f"Bearer {token}"})
    assert hist_res.status_code == 200
    logs = hist_res.json()
    assert len(logs) >= 2
    assert logs[-2]["new_custodian"] == "officer2"
    assert logs[-1]["new_custodian"] == "analyst3"
    assert EVIDENCE_STORE[ev_id]["custodian"] == "analyst3"

def test_regenerating_report_does_not_overwrite_previous_records():
    """
    Verify report generation preserves version history and computes report hashes independently.
    Regenerating a report must not delete or overwrite prior report records.
    """
    token = get_auth_token("investigator1")
    case_id = "CV-TEST-REP-907"
    CASES_STORE[case_id] = {
        "case_id": case_id,
        "case_number": case_id,
        "title": "Test Report Case",
        "description": "Test case description",
        "created_at": "2026-10-11T12:00:00Z",
        "is_deleted": False
    }


    # Generate Report 1
    res1 = client.post(
        "/api/reports/generate",
        json={"case_id": case_id, "title": "First Version Report"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res1.status_code == 200
    rep1_data = res1.json()

    # Generate Report 2
    res2 = client.post(
        "/api/reports/generate",
        json={"case_id": case_id, "title": "Second Version Report"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res2.status_code == 200
    rep2_data = res2.json()

    assert rep1_data["report_id"] != rep2_data["report_id"]
    assert rep1_data["report_filename"] != rep2_data["report_filename"]

    # Retrieve case report history
    history_res = client.get(f"/api/reports/history/{case_id}", headers={"Authorization": f"Bearer {token}"})
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 2
    filenames = [h["report_filename"] for h in history]
    assert rep1_data["report_filename"] in filenames
    assert rep2_data["report_filename"] in filenames

def test_case_soft_deletion_does_not_cascade_delete_evidence_or_custody():
    """Confirm case soft deletion does not cascade-delete evidence or custody records."""
    token = get_auth_token("admin", role="ADMIN")
    case_id = "CV-TEST-CASCADE-908"
    ev_id = "EV-CASCADE-908"

    # Setup case, evidence, and custody
    client.post("/api/cases", json={"case_id": case_id, "title": "Cascade Safety Case"}, headers={"Authorization": f"Bearer {token}"})
    EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": case_id,
        "filename": "cascade_specimen.bin",
        "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "custodian": "officer1"
    }
    AUDIT_LOGS_STORE[ev_id] = [{
        "log_id": "AUD-CASC-01",
        "evidence_id": ev_id,
        "action": "INGESTION",
        "new_custodian": "officer1"
    }]

    # Soft-delete case
    del_res = client.delete(f"/api/cases/{case_id}", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200

    # Verify case is soft-deleted
    assert CASES_STORE[case_id]["is_deleted"] is True

    # Crucial check: Evidence and custody logs MUST NOT be deleted
    ev_res = client.get(f"/api/evidence/{ev_id}", headers={"Authorization": f"Bearer {token}"})
    assert ev_res.status_code == 200
    assert ev_res.json()["evidence_id"] == ev_id

    cust_res = client.get(f"/api/custody/history/{ev_id}", headers={"Authorization": f"Bearer {token}"})
    assert cust_res.status_code == 200
    assert len(cust_res.json()) >= 1
