"""
ChainVault Phase 5 — Verifiable Forensic Report & Independent Report Integrity Verification Test Suite
======================================================================================================
Comprehensive automated tests covering:
1. Successful report generation for valid synthetic evidence.
2. Report metadata persistence and retrieval.
3. Correct PDF checksum calculation.
4. Detection of a modified PDF (PDF bitstream tampering).
5. Evidence file tampering before report generation.
6. Blockchain mismatch, missing registration, and RPC unavailability.
7. Custody audit-chain tampering or missing events.
8. Missing evidence, case, or report metadata & path traversal defense.
9. MongoDB unavailable when persistent storage is required.
10. Report-file write failure and metadata-write failure rollback.
11. QR URL configuration and missing public base URL.
12. Unauthorized access and RBAC enforcement.
13. Long hashes, long filenames, and multi-page custody histories.
14. Regression coverage for all existing functionality.
"""

import io
import os
import re
import time
import hashlib
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.routes.evidence import EVIDENCE_STORE
from app.routes.custody import AUDIT_LOGS_STORE
from app.routes.reports import REPORTS_REGISTRY
from app.database.mongodb import db_client
from app.services.blockchain import (
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS
)
from app.services.audit_trail import (
    record_custody_event,
    calculate_canonical_event_hash
)
from app.services.report import (
    get_reports_dir,
    resolve_verification_url,
    generate_qr_image,
    generate_pdf_report
)

client = TestClient(app)

SYNTHETIC_EVIDENCE_PREFIX = "EV-PH5-"
SYNTHETIC_CASE_PREFIX = "CV-PH5-"

def get_token(username="investigator1", role="INVESTIGATOR"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200, f"Authentication failed for {username}: {res.text}"
    return res.json()["access_token"]

@pytest.fixture(autouse=True)
def cleanup_phase5_synthetic_state():
    """Ensure all synthetic test records, evidence files, and report files are cleaned up."""
    reports_created = []

    def _cleanup():
        # Clean evidence stores
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

        # Clean reports registry
        to_remove = [r for r in list(REPORTS_REGISTRY) if r.get("case_id", "").startswith(SYNTHETIC_CASE_PREFIX)]
        for r in to_remove:
            if r in REPORTS_REGISTRY:
                REPORTS_REGISTRY.remove(r)
            fn = r.get("report_filename")
            if fn:
                p = get_reports_dir() / fn
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

    _cleanup()
    yield
    _cleanup()

def create_synthetic_evidence_file(name: str, content: bytes) -> str:
    """Create a temporary physical evidence file and return its path."""
    reports_dir = get_reports_dir()
    evidence_dir = reports_dir.parent / "storage" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    fp = evidence_dir / name
    fp.write_bytes(content)
    return str(fp)

def setup_valid_synthetic_record(ev_id="EV-PH5-001", case_id="CV-PH5-001", content=b"Phase 5 Forensic Integrity Content"):
    """Set up matching physical file, DB record, blockchain ledger, and custody audit record."""
    file_hash = hashlib.sha256(content).hexdigest()
    file_path = create_synthetic_evidence_file(f"{ev_id}.bin", content)

    # In-memory evidence store
    ev_record = {
        "evidence_id": ev_id,
        "case_id": case_id,
        "filename": f"{ev_id}.bin",
        "file_path": file_path,
        "file_hash": file_hash,
        "file_size": len(content),
        "custodian": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "uploaded_at": "2026-10-15T10:00:00Z",
        "blockchain_registered": True,
        "blockchain_tx": "0x" + hashlib.sha256(f"tx:{ev_id}".encode()).hexdigest(),
        "block_number": 100
    }
    EVIDENCE_STORE[ev_id] = ev_record

    # Mocked on-chain contract record
    CHAIN_EVIDENCE_STORE[ev_id] = {
        "evidence_id": ev_id,
        "case_id": case_id,
        "file_hash": file_hash,
        "custodian": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "registered_at": int(time.time()),
        "contract_address": CONTRACT_ADDRESS,
        "chain_id": EXPECTED_CHAIN_ID,
        "tx_hash": ev_record["blockchain_tx"],
        "block_number": 100,
        "status": "confirmed"
    }

    # Initial genesis custody audit event
    genesis_details = {
        "file_hash": file_hash,
        "filename": f"{ev_id}.bin",
        "previous_custodian": "None",
        "new_custodian": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "reason": "Initial digital evidence ingestion"
    }
    event_dict = {
        "event_id": f"AUD-{ev_id}-001",
        "evidence_id": ev_id,
        "case_id": case_id,
        "sequence_number": 1,
        "action": "EVIDENCE_INGESTION",
        "actor_id": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "previous_event_hash": "GENESIS",
        "details": genesis_details,
        "timestamp": "2026-10-15T10:00:00Z",
        "schema_version": 1
    }
    event_dict["event_hash"] = calculate_canonical_event_hash(event_dict)
    event_dict["blockchain_tx"] = ev_record["blockchain_tx"]
    AUDIT_LOGS_STORE[ev_id] = [event_dict]

    return ev_record, file_path, file_hash

# =============================================================================
# 1. SUCCESSFUL REPORT GENERATION FOR VALID SYNTHETIC EVIDENCE
# =============================================================================

def test_01_successful_report_generation_for_valid_synthetic_evidence():
    """Verify successful report generation for valid synthetic evidence with full verification."""
    ev_record, file_path, file_hash = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"], "title": "Forensic Trial Report"},
        headers=headers
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "success"
    assert data["verification_status"] == "VERIFIED"
    assert data["report_label"] == "VERIFIED"
    assert data["case_id"] == ev_record["case_id"]
    assert data["evidence_id"] == ev_record["evidence_id"]
    assert data["report_id"].startswith(f"REP-{ev_record['case_id']}")
    assert data["report_filename"].endswith(".pdf")
    assert len(data["report_hash"]) == 64

    # Check file exists on disk and starts with %PDF magic header
    report_file = get_reports_dir() / data["report_filename"]
    assert report_file.exists()
    content = report_file.read_bytes()
    assert content.startswith(b"%PDF")
    assert hashlib.sha256(content).hexdigest() == data["report_hash"]

# =============================================================================
# 2. REPORT METADATA PERSISTENCE AND RETRIEVAL
# =============================================================================

def test_02_report_metadata_persistence_and_retrieval():
    """Verify report metadata persistence, detail retrieval, and history querying."""
    ev_record, _, _ = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    rep_id = gen_data["report_id"]

    # Retrieve specific report detail
    detail_res = client.get(f"/api/reports/detail/{rep_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["report_id"] == rep_id
    assert detail["case_id"] == ev_record["case_id"]
    assert detail["evidence_id"] == ev_record["evidence_id"]
    assert detail["schema_version"] == "1.0.0"
    assert detail["verification_status"] == "VERIFIED"
    assert "report_path" not in detail  # Absolute disk path must not be exposed

    # Retrieve case history
    hist_res = client.get(f"/api/reports/history/{ev_record['case_id']}", headers=headers)
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert any(h["report_id"] == rep_id for h in history)

# =============================================================================
# 3. CORRECT PDF CHECKSUM CALCULATION
# =============================================================================

def test_03_correct_pdf_checksum_calculation():
    """Verify that returned report_hash matches independent calculation from downloaded file bytes."""
    ev_record, _, _ = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    gen_data = gen_res.json()
    rep_hash = gen_data["report_hash"]
    filename = gen_data["report_filename"]

    # Download report via API
    down_res = client.get(f"/api/reports/download/{filename}", headers=headers)
    assert down_res.status_code == 200
    downloaded_bytes = down_res.content

    computed_hash = hashlib.sha256(downloaded_bytes).hexdigest()
    assert computed_hash == rep_hash, f"Checksum mismatch: {computed_hash} != {rep_hash}"

# =============================================================================
# 4. DETECTION OF A MODIFIED PDF (TAMPERING)
# =============================================================================

def test_04_detection_of_modified_pdf():
    """Verify detection of a modified PDF file bitstream during independent verification."""
    ev_record, _, _ = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    gen_data = gen_res.json()
    rep_id = gen_data["report_id"]
    filename = gen_data["report_filename"]

    # Initial verification: Should be INTACT / VERIFIED
    verify_init = client.get(f"/api/reports/verify/{rep_id}", headers=headers)
    assert verify_init.status_code == 200
    v1 = verify_init.json()
    assert v1["report_verification_status"] == "VERIFIED"
    assert v1["pdf_integrity"]["checksum_matches"] is True
    assert v1["pdf_integrity"]["file_status"] == "INTACT"
    assert v1["pdf_integrity"]["is_digitally_signed"] is False

    # Tamper with the PDF file on disk
    report_file = get_reports_dir() / filename
    assert report_file.exists()
    with open(report_file, "ab") as f:
        f.write(b"\n% TAMPERED_BYTE_INJECTION_FOR_FORENSIC_INTEGRITY_TEST")

    # Re-verify modified report
    verify_tampered = client.get(f"/api/reports/verify/{rep_id}", headers=headers)
    assert verify_tampered.status_code == 200
    v2 = verify_tampered.json()
    assert v2["report_verification_status"] == "TAMPERED"
    assert v2["pdf_integrity"]["checksum_matches"] is False
    assert v2["pdf_integrity"]["file_status"] == "TAMPERED"
    assert v2["technical_error"] == "PDF_CHECKSUM_MISMATCH"
    assert "modified" in v2["explanation"].lower()

# =============================================================================
# 5. EVIDENCE FILE TAMPERING BEFORE REPORT GENERATION
# =============================================================================

def test_05_evidence_file_tampering_before_report_generation():
    """Verify that tampering with physical evidence before generation labels the report TAMPERED."""
    ev_record, file_path, _ = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    # Alter the physical file on disk before generation
    with open(file_path, "wb") as f:
        f.write(b"CORRUPTED_TAMPERED_BYTE_STREAM")

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    # Verification status must be TAMPERED (never VERIFIED)
    assert gen_data["verification_status"] == "TAMPERED"
    assert "INCOMPLETE / UNVERIFIED (TAMPERED)" in gen_data["report_label"]
    assert gen_data["discrepancies_count"] >= 1

    # Verify report independent check also flags evidence tampering
    rep_id = gen_data["report_id"]
    verif_res = client.get(f"/api/reports/verify/{rep_id}", headers=headers)
    assert verif_res.status_code == 200
    v_data = verif_res.json()
    assert v_data["report_verification_status"] == "TAMPERED"

# =============================================================================
# 6. BLOCKCHAIN MISMATCH, MISSING REGISTRATION, AND RPC UNAVAILABILITY
# =============================================================================

def test_06_blockchain_unregistered_produces_inconsistent_report():
    """Verify evidence not anchored on blockchain generates INCONSISTENT report (never VERIFIED)."""
    ev_record, _, _ = setup_valid_synthetic_record()
    # Remove from blockchain store
    CHAIN_EVIDENCE_STORE.pop(ev_record["evidence_id"], None)

    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["verification_status"] == "INCONSISTENT"
    assert "INCOMPLETE / UNVERIFIED (INCONSISTENT)" in gen_data["report_label"]

def test_06_blockchain_rpc_unavailability_produces_unavailable_report(monkeypatch):
    """Verify that when blockchain RPC is offline, report generation marks status UNAVAILABLE."""
    from app.services import blockchain

    ev_record, _, _ = setup_valid_synthetic_record()

    # Simulate blockchain RPC offline across services
    monkeypatch.setattr("app.services.blockchain.get_independent_blockchain_record", lambda *args, **kwargs: (None, "RPC_UNAVAILABLE"))
    monkeypatch.setattr("app.routes.verification.get_independent_blockchain_record", lambda *args, **kwargs: (None, "RPC_UNAVAILABLE"))
    monkeypatch.setattr("app.services.audit_trail.get_independent_blockchain_record", lambda *args, **kwargs: (None, "RPC_UNAVAILABLE"))

    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["verification_status"] == "UNAVAILABLE"
    assert "INCOMPLETE / UNVERIFIED (UNAVAILABLE)" in gen_data["report_label"]

# =============================================================================
# 7. CUSTODY AUDIT-CHAIN TAMPERING OR MISSING EVENTS
# =============================================================================

def test_07_custody_audit_chain_tampering_produces_tampered_report():
    """Verify that tampering with a custody audit event flags the report as TAMPERED."""
    ev_record, _, _ = setup_valid_synthetic_record()
    eid = ev_record["evidence_id"]

    # Tamper with the custody audit event's action and stored hash
    assert eid in AUDIT_LOGS_STORE
    event = AUDIT_LOGS_STORE[eid][0]
    event["action"] = "UNAUTHORIZED_CUSTODY_TRANSFER"
    # Do not recalculate event_hash -> creates hash tampering

    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": eid},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["verification_status"] == "TAMPERED"
    assert "INCOMPLETE / UNVERIFIED (TAMPERED)" in gen_data["report_label"]
    assert gen_data["discrepancies_count"] >= 1

# =============================================================================
# 8. MISSING EVIDENCE, CASE, OR REPORT METADATA & PATH TRAVERSAL DEFENSE
# =============================================================================

def test_08_missing_evidence_yields_404():
    """Verify requesting report for non-existent evidence returns HTTP 404."""
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/reports/generate",
        json={"case_id": "CV-PH5-NONEXISTENT", "evidence_id": "EV-PH5-NONEXISTENT-999"},
        headers=headers
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

def test_08_nonexistent_report_verify_returns_not_found():
    """Verify verifying a non-existent report ID returns structured NOT_FOUND."""
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/reports/verify/REP-NONEXISTENT-999", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["report_verification_status"] == "NOT_FOUND"
    assert data["report_found"] is False
    assert data["technical_error"] == "REPORT_RECORD_NOT_FOUND"

def test_08_path_traversal_defense_on_report_endpoints():
    """Verify that path traversal attempts in report endpoints are strictly rejected."""
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    # Traversal in download
    res_dl = client.get("/api/reports/download/..%2F..%2Fsecret.txt", headers=headers)
    assert res_dl.status_code in (400, 404)

    # Traversal in verify GET
    res_vg = client.get("/api/reports/verify/..%2F..%2Fetc%2Fpasswd", headers=headers)
    assert res_vg.status_code in (400, 404)

    # Traversal in verify POST
    res_vp = client.post(
        "/api/reports/verify",
        json={"report_id": "../../windows/system32/cmd.exe"},
        headers=headers
    )
    assert res_vp.status_code == 400

# =============================================================================
# 9. MONGODB UNAVAILABLE WHEN PERSISTENT STORAGE IS REQUIRED
# =============================================================================

def test_09_mongodb_unavailable_when_persistent_storage_required(monkeypatch):
    """Verify that report generation fails closed (HTTP 503) when persistent storage is required and DB is offline."""
    ev_record, _, _ = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    # Simulate REQUIRE_PERSISTENT_STORAGE=true and DB disconnected
    monkeypatch.setattr(db_client, "require_persistent_storage", True)
    monkeypatch.setattr(db_client, "is_connected", lambda: False)

    res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    assert res.status_code == 503
    assert "persistent database storage is required" in res.json()["detail"].lower()

# =============================================================================
# 10. ATOMIC ROLLBACK ON PERSISTENCE WRITE FAILURE
# =============================================================================

def test_10_metadata_write_failure_cleans_up_new_pdf_file(monkeypatch):
    """Verify that if PDF is written but DB persistence fails, the newly created PDF file is cleaned up."""
    ev_record, file_path, _ = setup_valid_synthetic_record()
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    # Track report files before test
    reports_dir = get_reports_dir()
    existing_files = set(reports_dir.glob("*.pdf"))

    # Mock DB insert failure
    async def mock_failed_insert(*args, **kwargs):
        raise RuntimeError("Simulated Database I/O Write Failure")

    monkeypatch.setattr(db_client, "is_connected", lambda: True)
    monkeypatch.setattr(db_client, "reports", type("MockCollection", (), {"insert_one": mock_failed_insert})())

    res = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=headers
    )
    assert res.status_code in (500, 503)

    # Verify no orphaned PDF file was left behind
    current_files = set(reports_dir.glob("*.pdf"))
    assert current_files == existing_files, "Newly generated report file was not cleaned up after DB error!"

    # Verify evidence file was NOT touched or deleted
    assert os.path.exists(file_path), "Evidence file was deleted during rollback!"

# =============================================================================
# 11. QR URL CONFIGURATION AND MISSING PUBLIC BASE URL
# =============================================================================

def test_11_qr_url_configuration_and_missing_public_base_url(monkeypatch):
    """Verify configurable QR code URL resolution, local dev warning, and public URL fallback."""
    import app.services.report as rep_mod

    # Case 1: Configured Public Base URL
    monkeypatch.setattr(rep_mod, "PUBLIC_VERIFICATION_URL_BASE", "https://forensic.chainvault.org")
    url_pub, is_local_pub, note_pub = rep_mod.resolve_verification_url("REP-001", is_report=True)
    assert url_pub == "https://forensic.chainvault.org/api/reports/verify/REP-001"
    assert is_local_pub is False
    assert "Public" in note_pub

    # Case 2: Local Development Link (PUBLIC_VERIFICATION_URL_BASE empty, ALLOW_LOCAL_QR_LINKS=True)
    monkeypatch.setattr(rep_mod, "PUBLIC_VERIFICATION_URL_BASE", None)
    monkeypatch.setattr(rep_mod, "ALLOW_LOCAL_QR_LINKS", True)
    monkeypatch.setattr(rep_mod, "LOCAL_VERIFICATION_URL_BASE", "http://localhost:8000")
    url_loc, is_local_loc, note_loc = rep_mod.resolve_verification_url("REP-001", is_report=True)
    assert url_loc == "http://localhost:8000/api/reports/verify/REP-001"
    assert is_local_loc is True
    assert "Local Development Link" in note_loc

    # Case 3: Public links disabled (ALLOW_LOCAL_QR_LINKS=False, no public URL)
    monkeypatch.setattr(rep_mod, "PUBLIC_VERIFICATION_URL_BASE", None)
    monkeypatch.setattr(rep_mod, "ALLOW_LOCAL_QR_LINKS", False)
    url_dis, is_local_dis, note_dis = rep_mod.resolve_verification_url("REP-001", is_report=True)
    assert url_dis == ""
    assert is_local_dis is False
    assert "Unconfigured" in note_dis

    # Verify QR image generation produces valid PNG bytes in all cases
    qr_bytes = rep_mod.generate_qr_image("EV-001")
    assert qr_bytes.startswith(b"\x89PNG")

# =============================================================================
# 12. UNAUTHORIZED ACCESS AND RBAC ENFORCEMENT
# =============================================================================

def test_12_unauthorized_access_and_rbac_enforcement():
    """Verify RBAC: Viewer cannot compile reports; unauthenticated requests are rejected."""
    # 1. Unauthenticated requests
    res_noauth_gen = client.post("/api/reports/generate", json={"case_id": "CV-PH5-001"})
    assert res_noauth_gen.status_code == 401

    res_noauth_dl = client.get("/api/reports/download/report.pdf")
    assert res_noauth_dl.status_code == 401

    res_noauth_vf = client.get("/api/reports/verify/REP-001")
    assert res_noauth_vf.status_code == 401

    # 2. VIEWER role cannot generate reports (forbidden)
    viewer_token = get_token("viewer1", role="VIEWER")
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    res_viewer_gen = client.post(
        "/api/reports/generate",
        json={"case_id": "CV-PH5-001"},
        headers=viewer_headers
    )
    assert res_viewer_gen.status_code == 403
    assert "lacks permission" in res_viewer_gen.json()["detail"].lower()

    # 3. ANALYST, INVESTIGATOR, ADMIN can generate reports
    analyst_token = get_token("analyst1", role="ANALYST")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    ev_record, _, _ = setup_valid_synthetic_record()

    res_analyst_gen = client.post(
        "/api/reports/generate",
        json={"case_id": ev_record["case_id"], "evidence_id": ev_record["evidence_id"]},
        headers=analyst_headers
    )
    assert res_analyst_gen.status_code == 200

# =============================================================================
# 13. LONG HASHES, LONG FILENAMES, AND MULTI-PAGE CUSTODY HISTORIES
# =============================================================================

def test_13_long_hashes_long_filenames_and_multi_page_custody():
    """Verify that lengthy metadata, long filenames, and 30 custody transfers paginate gracefully."""
    ev_record, _, _ = setup_valid_synthetic_record()
    eid = ev_record["evidence_id"]
    cid = ev_record["case_id"]

    # Update evidence to have very long filename
    ev_record["filename"] = "VERY_LONG_FORENSIC_ACQUISITION_DISK_IMAGE_SECTOR_0_STREAM_E01_FINAL_RAW_IMAGE.raw.bin"

    # Add 25 chain of custody transfer events to force multi-page layout
    logs = list(AUDIT_LOGS_STORE[eid])
    last_hash = logs[0]["event_hash"]
    for i in range(1, 25):
        ev_item = {
            "event_id": f"AUD-{eid}-{i+1:03d}",
            "evidence_id": eid,
            "case_id": cid,
            "sequence_number": i + 1,
            "action": "CUSTODY_TRANSFER",
            "actor_id": f"0x{(i):040x}",
            "previous_event_hash": last_hash,
            "details": {
                "previous_custodian": f"0x{(i):040x}",
                "new_custodian": f"0x{(i+1):040x}",
                "reason": f"Custody transfer handover stage {i}"
            },
            "timestamp": f"2026-10-15T12:{i:02d}:00Z",
            "schema_version": 1
        }
        ev_item["event_hash"] = calculate_canonical_event_hash(ev_item)
        ev_item["blockchain_tx"] = f"0x{hashlib.sha256(str(i).encode()).hexdigest()}"
        last_hash = ev_item["event_hash"]
        logs.append(ev_item)

    AUDIT_LOGS_STORE[eid] = logs

    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/reports/generate",
        json={"case_id": cid, "evidence_id": eid},
        headers=headers
    )
    assert res.status_code == 200
    gen_data = res.json()
    assert gen_data["verification_status"] == "VERIFIED"

    # Verify multi-page generation
    rep_file = get_reports_dir() / gen_data["report_filename"]
    pdf_bytes = rep_file.read_bytes()
    page_matches = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert len(page_matches) >= 2, f"Expected multi-page PDF, got {len(page_matches)}"
    assert hashlib.sha256(pdf_bytes).hexdigest() == gen_data["report_hash"]

# =============================================================================
# 14. REGRESSION COVERAGE AND WORKFLOW RECONCILIATION
# =============================================================================

def test_14_full_forensic_report_and_verification_workflow():
    """Verify complete end-to-end workflow: evidence upload -> custody transfer -> report compilation -> verification."""
    token = get_token("investigator1")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload evidence
    test_content = b"Phase 5 Complete Workflow Specimen"
    up_res = client.post(
        "/api/evidence/upload",
        data={"case_id": "CV-PH5-WF-001", "description": "Workflow verification item"},
        files={"file": ("workflow_sample.bin", io.BytesIO(test_content), "application/octet-stream")},
        headers=headers
    )
    assert up_res.status_code == 201
    up_data = up_res.json()
    wf_ev_id = up_data["evidence_id"]

    # 2. Transfer custody
    cust_res = client.post(
        "/api/custody/transfer",
        json={
            "evidence_id": wf_ev_id,
            "new_custodian": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            "reason": "Transfer to forensic analysis division"
        },
        headers=headers
    )
    assert cust_res.status_code == 200

    # 3. Generate report
    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": "CV-PH5-WF-001", "evidence_id": wf_ev_id, "title": "End-to-End Workflow Report"},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    wf_rep_id = gen_data["report_id"]

    # 4. Verify report
    vf_res = client.get(f"/api/reports/verify/{wf_rep_id}", headers=headers)
    assert vf_res.status_code == 200
    vf_data = vf_res.json()
    assert vf_data["report_id"] == wf_rep_id
    assert vf_data["pdf_integrity"]["checksum_matches"] is True
    assert vf_data["pdf_integrity"]["file_status"] == "INTACT"
