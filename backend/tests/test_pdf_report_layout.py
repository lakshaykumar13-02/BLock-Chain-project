import io
import re
import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.report import generate_pdf_report
client = TestClient(app)

def get_auth_token(username="investigator1", role="INVESTIGATOR"):
    """Helper to authenticate and retrieve access token for tests."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200
    return res.json()["access_token"]

def test_pdf_starts_with_valid_pdf_magic_bytes():
    """Verify that generated report begins with standard %PDF magic bytes."""
    case_data = {
        "case_id": "CV-TEST-PDF-001",
        "title": "Basic PDF Validation Case",
        "description": "Standard synthetic test case",
        "lead_investigator": "investigator1"
    }
    path, pdf_bytes, rep_hash = generate_pdf_report(
        case_id="CV-TEST-PDF-001",
        case_data=case_data,
        evidence_items=[],
        audit_logs=[],
        preserve_existing=True
    )
    assert pdf_bytes.startswith(b"%PDF"), "Generated PDF does not start with %PDF magic header"
    assert len(pdf_bytes) > 500, "Generated PDF is suspiciously small"

def test_pdf_hash_matches_content_sha256():
    """Verify that returned report_hash matches independent SHA-256 calculation."""
    case_data = {
        "case_id": "CV-TEST-PDF-002",
        "title": "Cryptographic Hash Validation Case",
        "description": "Ensuring tamper-evident digest matches exact byte stream",
        "lead_investigator": "investigator1"
    }
    path, pdf_bytes, rep_hash = generate_pdf_report(
        case_id="CV-TEST-PDF-002",
        case_data=case_data,
        evidence_items=[],
        audit_logs=[],
        preserve_existing=True
    )
    computed_hash = hashlib.sha256(pdf_bytes).hexdigest()
    assert computed_hash == rep_hash, f"Hash mismatch: {computed_hash} != {rep_hash}"

def test_pdf_report_handles_long_text_and_descriptions():
    """Verify that long case titles, lengthy descriptions, and long filenames wrap cleanly."""
    long_desc = (
        "This is an extraordinarily detailed forensic summary describing the forensic acquisition "
        "of volatile system memory, unallocated disk clusters, and physical storage media. "
        "The investigation was initiated following automated detection of anomalous exfiltration traffic. "
        "All acquired binary artifacts were imaged in strict accordance with ISO/IEC 27037 standards, "
        "utilizing hardware-blocked write blockers to guarantee zero bitstream modification."
    ) * 3
    case_data = {
        "case_id": "CV-TEST-PDF-LONG-001",
        "title": "Comprehensive Cyber Intrusion Investigation with Extensive Descriptive Metadata Across Multiple Jurisdictions",
        "description": long_desc,
        "lead_investigator": "Supervisory Forensic Agent Alexander Hamilton Jr."
    }
    evidence_items = [{
        "evidence_id": "EV-LONG-001",
        "filename": "FORENSIC_RAW_BITSTREAM_DISK_IMAGE_SEIZED_FROM_TARGET_WORKSTATION_DRIVE_0_VOLUME_1.E01",
        "file_hash": "f693f6874e7ef95e89643bbf76cafdb06eba9c9aaf7592aafdd8ed8311cad135",
        "file_size": 104857600,
        "custodian": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
    }]
    path, pdf_bytes, rep_hash = generate_pdf_report(
        case_id="CV-TEST-PDF-LONG-001",
        case_data=case_data,
        evidence_items=evidence_items,
        audit_logs=[],
        preserve_existing=True
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert hashlib.sha256(pdf_bytes).hexdigest() == rep_hash

def test_pdf_report_handles_long_hashes_and_eth_addresses():
    """Verify that 64-char hashes and 42-char Ethereum addresses wrap inside table cells."""
    case_data = {
        "case_id": "CV-TEST-PDF-ADDR-001",
        "title": "Cryptographic Address Formatting Test",
        "description": "Verifying address wrapping and table cell containment",
        "lead_investigator": "investigator1"
    }
    evidence_items = [{
        "evidence_id": "EV-ADDR-001",
        "filename": "payload.dat",
        "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "file_size": 80,
        "custodian": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
    }]
    audit_logs = [{
        "log_id": "AUD-LONG-ADDR-001",
        "action": "CUSTODY_TRANSFER",
        "previous_custodian": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "new_custodian": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "timestamp": "2026-10-11T14:30:00.000000Z",
        "blockchain_tx": "0x9876543210abcdef9876543210abcdef9876543210abcdef9876543210abcdef"
    }]
    path, pdf_bytes, rep_hash = generate_pdf_report(
        case_id="CV-TEST-PDF-ADDR-001",
        case_data=case_data,
        evidence_items=evidence_items,
        audit_logs=audit_logs,
        preserve_existing=True
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert rep_hash == hashlib.sha256(pdf_bytes).hexdigest()

def test_pdf_report_multi_page_pagination_and_table_headers():
    """Verify that large audit histories paginate cleanly across multiple pages with repeated headers."""
    case_data = {
        "case_id": "CV-TEST-PDF-MULTI-001",
        "title": "Multi-Page Pagination and Repeating Header Verification",
        "description": "Stress testing pagination with 25 custody transfers",
        "lead_investigator": "investigator1"
    }
    evidence_items = [
        {
            "evidence_id": f"EV-MULTI-{i:03d}",
            "filename": f"disk_artifact_sector_{i}.bin",
            "file_hash": hashlib.sha256(f"evidence_{i}".encode()).hexdigest(),
            "file_size": 1024 * (i + 1),
            "custodian": f"0x{i:040x}"
        }
        for i in range(5)
    ]
    audit_logs = [
        {
            "log_id": f"AUD-MULTI-{i:03d}",
            "action": "CUSTODY_TRANSFER" if i > 0 else "EVIDENCE_INGESTION",
            "previous_custodian": f"0x{(i):040x}",
            "new_custodian": f"0x{(i+1):040x}",
            "timestamp": f"2026-10-11T12:{i:02d}:00Z",
            "blockchain_tx": f"0x{hashlib.sha256(str(i).encode()).hexdigest()}"
        }
        for i in range(25)
    ]
    path, pdf_bytes, rep_hash = generate_pdf_report(
        case_id="CV-TEST-PDF-MULTI-001",
        case_data=case_data,
        evidence_items=evidence_items,
        audit_logs=audit_logs,
        preserve_existing=True
    )
    # Count page objects in compiled PDF
    page_matches = re.findall(rb"/Type\s*/Page\b", pdf_bytes)
    assert len(page_matches) >= 2, f"Expected multiple pages, got {len(page_matches)}"
    assert rep_hash == hashlib.sha256(pdf_bytes).hexdigest()

def test_pdf_report_xml_special_characters_escaping():
    """Verify that XML special characters in user inputs (&, <, >, quotes) do not cause ExpatError."""
    case_data = {
        "case_id": "CV-TEST-XML-001",
        "title": "Test with Special Chars: & < > \" ' &amp; &lt;",
        "description": "Malicious or unusual characters: <script>alert('xss')</script> & <b>bold</b> & 'quoted'",
        "lead_investigator": "investigator1 & partner"
    }
    evidence_items = [{
        "evidence_id": "EV-XML-001",
        "filename": "file_with_&_<_>_chars.dat",
        "file_hash": "f693f6874e7ef95e89643bbf76cafdb06eba9c9aaf7592aafdd8ed8311cad135",
        "file_size": 80,
        "custodian": "officer<1>&partner"
    }]
    audit_logs = [{
        "log_id": "AUD-XML-001",
        "action": "TRANSFER & VERIFY",
        "previous_custodian": "officer<1>",
        "new_custodian": "officer<2>",
        "timestamp": "2026-10-11T10:00:00Z",
        "blockchain_tx": "0x123&456"
    }]
    path, pdf_bytes, rep_hash = generate_pdf_report(
        case_id="CV-TEST-XML-001",
        case_data=case_data,
        evidence_items=evidence_items,
        audit_logs=audit_logs,
        preserve_existing=True
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert rep_hash == hashlib.sha256(pdf_bytes).hexdigest()

def test_pdf_report_api_endpoint_end_to_end():
    """Verify that POST /api/reports/generate and GET /api/reports/download work seamlessly end-to-end."""
    token = get_auth_token("investigator1", role="INVESTIGATOR")
    headers = {"Authorization": f"Bearer {token}"}
    
    gen_res = client.post(
        "/api/reports/generate",
        json={"case_id": "CV-DEMO-2026-001", "title": "End-to-End Layout Validation"},
        headers=headers
    )
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["status"] == "success"
    filename = gen_data["report_filename"]
    reported_hash = gen_data["report_hash"]
    
    # Download report
    down_res = client.get(f"/api/reports/download/{filename}", headers=headers)
    assert down_res.status_code == 200
    down_bytes = down_res.content
    assert down_bytes.startswith(b"%PDF")
    assert hashlib.sha256(down_bytes).hexdigest() == reported_hash
