import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_auth_login_endpoint_exists():
    """Requirement 3.A: Authentication endpoint exists."""
    response = client.post("/api/auth/login", json={"username": "admin", "password": "password"})
    assert response.status_code != 404

def test_case_crud_endpoint_exists():
    """Requirement 3.A: Case creation endpoint exists."""
    response = client.post("/api/cases", json={"title": "Test Case", "description": "Test"})
    assert response.status_code != 404

def test_evidence_upload_endpoint_exists():
    """Requirement 3.B: Evidence upload endpoint exists."""
    response = client.post("/api/evidence/upload")
    assert response.status_code != 404

def test_custody_transfer_endpoint_exists():
    """Requirement 3.D: Chain of custody transfer endpoint exists."""
    response = client.post("/api/custody/transfer", json={})
    assert response.status_code != 404

def test_verification_endpoint_exists():
    """Requirement 3.E: Three-way integrity verification endpoint exists."""
    response = client.post("/api/verification/verify", json={})
    assert response.status_code != 404

def test_report_generation_endpoint_exists():
    """Requirement 3.F: Forensic report generation endpoint exists."""
    response = client.post("/api/reports/generate", json={})
    assert response.status_code != 404
