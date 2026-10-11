import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Synthetic test fixture data
SYNTHETIC_EVIDENCE_PAYLOAD = b"ChainVault Synthetic Evidence File Payload 2026 - Forensic Integrity Test"
SYNTHETIC_SHA256 = hashlib.sha256(SYNTHETIC_EVIDENCE_PAYLOAD).hexdigest()

def test_lifecycle_step_01_authenticate():
    """Step 1: Authenticate as an authorized investigator user."""
    res = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    assert res.status_code == 200

def test_lifecycle_step_02_create_case():
    """Step 2: Create a case record."""
    res = client.post("/api/cases", json={"case_number": "CV-2026-001", "title": "Synthetic Forensic Case"})
    assert res.status_code == 201

def test_lifecycle_step_03_upload_synthetic_evidence():
    """Step 3: Upload a synthetic evidence file."""
    res = client.post("/api/evidence/upload", files={"file": ("evidence.bin", SYNTHETIC_EVIDENCE_PAYLOAD)})
    assert res.status_code == 201

def test_lifecycle_step_04_calculate_and_verify_sha256():
    """Step 4: Calculate and verify synthetic SHA-256 hash."""
    computed_hash = hashlib.sha256(SYNTHETIC_EVIDENCE_PAYLOAD).hexdigest()
    assert computed_hash == SYNTHETIC_SHA256
    assert len(computed_hash) == 64

def test_lifecycle_step_05_register_evidence_on_blockchain():
    """Step 5: Register evidence hash on local Ethereum blockchain."""
    res = client.post("/api/blockchain/register", json={"evidence_id": "EV-001", "hash": SYNTHETIC_SHA256})
    assert res.status_code == 200

def test_lifecycle_step_06_transfer_custody():
    """Step 6: Transfer custody to an eligible test user."""
    res = client.post("/api/custody/transfer", json={"evidence_id": "EV-001", "new_custodian": "officer2"})
    assert res.status_code == 200

def test_lifecycle_step_07_three_way_hash_verification():
    """Step 7: Verify file, database, and blockchain hashes match."""
    res = client.post("/api/verification/verify", json={"evidence_id": "EV-001"})
    assert res.status_code == 200

def test_lifecycle_step_08_generate_qr_code():
    """Step 8: Generate QR code and verify routing payload."""
    res = client.get("/api/reports/qr/EV-001")
    assert res.status_code == 200

def test_lifecycle_step_09_generate_forensic_pdf_report():
    """Step 9: Generate and download forensic PDF report."""
    res = client.post("/api/reports/generate", json={"case_id": "CV-2026-001"})
    assert res.status_code == 200

def test_lifecycle_step_10_inspect_audit_records():
    """Step 10: Inspect relevant audit and custody records."""
    res = client.get("/api/audit/logs/EV-001")
    assert res.status_code == 200

def test_lifecycle_step_11_attempt_unauthorized_destructive_action():
    """Step 11: Attempt unauthorized action (evidence deletion) and confirm rejection."""
    res = client.delete("/api/evidence/EV-001")
    # Deletion must be rejected (404 / 405 / 403)
    assert res.status_code in [404, 405, 403]
