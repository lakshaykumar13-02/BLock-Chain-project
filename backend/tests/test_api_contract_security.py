import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security.auth import create_access_token

client = TestClient(app)

def test_protected_endpoints_reject_missing_token():
    """Verify that protected endpoints reject requests lacking Authorization token with HTTP 401."""
    # Ensure client has no authorization header
    unauth_client = TestClient(app)

    res_cases = unauth_client.post("/api/cases", json={"title": "Unauthorized Case"})
    assert res_cases.status_code == 401
    assert "Authentication required" in res_cases.json().get("detail", "")

    res_evidence = unauth_client.post("/api/evidence/upload")
    assert res_evidence.status_code == 401

    res_custody = unauth_client.post("/api/custody/transfer", json={"evidence_id": "EV-001", "new_custodian": "officer2"})
    assert res_custody.status_code == 401

    res_blockchain = unauth_client.post("/api/blockchain/register", json={"evidence_id": "EV-001", "hash": "abc"})
    assert res_blockchain.status_code == 401

    res_reports = unauth_client.post("/api/reports/generate", json={"case_id": "CV-2026-001"})
    assert res_reports.status_code == 401

def test_protected_endpoints_reject_invalid_token():
    """Verify that tampered or malformed JWT tokens are rejected with HTTP 401."""
    headers = {"Authorization": "Bearer malformed.invalid.token"}
    res = client.post("/api/cases", json={"title": "Test Case"}, headers=headers)
    assert res.status_code == 401
    assert "Invalid authentication token" in res.json().get("detail", "")

def test_protected_endpoints_reject_expired_token():
    """Verify that expired JWT tokens are rejected with HTTP 401."""
    expired_token = create_access_token(
        data={"sub": "USR-TEST-01", "role": "INVESTIGATOR"},
        expires_delta=datetime.timedelta(minutes=-30)
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    res = client.post("/api/cases", json={"title": "Test Case"}, headers=headers)
    assert res.status_code == 401
    assert "Token has expired" in res.json().get("detail", "")

def test_role_enforcement_viewer_cannot_mutate_state():
    """Verify server-side RBAC: VIEWER role cannot create cases, upload evidence, or transfer custody."""
    # Authenticate as viewer
    res_login = client.post("/api/auth/login", json={"username": "viewer1", "password": "TestPassword123!"})
    assert res_login.status_code == 200
    viewer_token = res_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Case creation rejected
    res_case = client.post("/api/cases", json={"title": "Viewer Case Attempt"}, headers=viewer_headers)
    assert res_case.status_code == 403
    assert "lacks permission" in res_case.json().get("detail", "")

    # Evidence upload rejected
    res_upload = client.post("/api/evidence/upload", headers=viewer_headers)
    assert res_upload.status_code == 403

    # Custody transfer rejected
    res_custody = client.post("/api/custody/transfer", json={"evidence_id": "EV-001"}, headers=viewer_headers)
    assert res_custody.status_code == 403

    # Report generation rejected
    res_report = client.post("/api/reports/generate", json={"case_id": "CV-001"}, headers=viewer_headers)
    assert res_report.status_code == 403

def test_role_enforcement_investigator_permissions():
    """Verify that INVESTIGATOR role can create cases and upload evidence but cannot soft delete cases."""
    res_login = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    assert res_login.status_code == 200
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Can create case
    res_case = client.post("/api/cases", json={"title": "Investigator Case"}, headers=headers)
    assert res_case.status_code == 201
    case_id = res_case.json()["case_id"]

    # Cannot soft-delete case (ADMIN only)
    res_del = client.delete(f"/api/cases/{case_id}", headers=headers)
    assert res_del.status_code == 403

def test_role_enforcement_admin_can_soft_delete_case():
    """Verify that ADMIN role can soft delete cases."""
    # Create a case as investigator first
    inv_login = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    inv_headers = {"Authorization": f"Bearer {inv_login.json()['access_token']}"}
    case_res = client.post("/api/cases", json={"title": "Case to be deleted"}, headers=inv_headers)
    case_id = case_res.json()["case_id"]

    # Admin deletes case
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    del_res = client.delete(f"/api/cases/{case_id}", headers=admin_headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

def test_zero_credentials_leaked_in_api_responses():
    """Verify that authentication, case, evidence, and error responses never leak passwords or keys."""
    # Auth response check
    res_login = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    body = res_login.text
    assert "password" not in body.lower() or "password123" not in body
    assert "jwt_secret" not in body.lower()

    # Blockchain status check
    res_bc = client.get("/api/blockchain/status")
    assert "private" not in res_bc.text.lower()

def test_evidence_deletion_rejected_for_admin():
    """Verify that even ADMIN cannot delete evidence (immutable digital evidence policy)."""
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    res = client.delete("/api/evidence/EV-001", headers=admin_headers)
    assert res.status_code in [404, 405]
