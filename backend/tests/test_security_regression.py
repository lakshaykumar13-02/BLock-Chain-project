import io
import os
import jwt
import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.routes.auth import DEMO_USERS
from app.security.auth import JWT_SECRET, JWT_ALGORITHM
from app.routes.cases import CASES_STORE
from app.routes.evidence import EVIDENCE_STORE
from app.security.permissions import UserRole

client = TestClient(app)

def get_auth_token(username="investigator1"):
    """Helper to authenticate and return a valid JWT access token."""
    pwd = "AdminPassword123!" if username == "admin" else "TestPassword123!"
    res = client.post("/api/auth/login", json={"username": username, "password": pwd})
    assert res.status_code == 200, f"Auth failed for {username}: {res.text}"
    return res.json()["access_token"]

# ==============================================================================
# SECTION 2: AUTHENTICATION TESTS
# ==============================================================================

def test_login_valid_credentials():
    """Verify valid login returns 200, JWT token, and correct user role."""
    res = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["role"] == "INVESTIGATOR"
    assert data["user_id"] == "USR-INV-01"

def test_login_invalid_credentials():
    """Verify incorrect password returns 401 Unauthorized."""
    res = client.post("/api/auth/login", json={"username": "investigator1", "password": "WrongPassword!"})
    assert res.status_code == 401
    assert "detail" in res.json()

def test_login_nonexistent_user():
    """Verify nonexistent user returns 401 Unauthorized."""
    res = client.post("/api/auth/login", json={"username": "ghost_officer", "password": "Password123!"})
    assert res.status_code == 401

def test_password_stored_as_bcrypt_hash_not_plaintext():
    """Verify passwords in system records are stored as bcrypt hashes starting with $2b$."""
    for uname, udata in DEMO_USERS.items():
        assert "password" not in udata, f"Plaintext password found in user record: {uname}"
        assert "password_hash" in udata, f"password_hash missing in user record: {uname}"
        assert udata["password_hash"].startswith("$2b$"), f"Hash is not bcrypt format for {uname}"

def test_missing_auth_token_rejected():
    """Verify protected endpoints reject requests lacking Authorization header with 401."""
    res = client.post("/api/cases", json={"title": "Unauthorized Case"})
    assert res.status_code == 401

def test_malformed_auth_token_rejected():
    """Verify malformed bearer tokens return 401 Unauthorized."""
    res = client.get("/api/cases", headers={"Authorization": "Bearer not-a-valid-jwt-token"})
    assert res.status_code == 401

def test_expired_auth_token_rejected():
    """Verify expired JWTs return 401 Unauthorized."""
    past_exp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    expired_token = jwt.encode(
        {"sub": "USR-INV-01", "username": "investigator1", "role": "INVESTIGATOR", "exp": past_exp},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM
    )
    res = client.get("/api/cases", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower()

def test_inactive_user_login_rejected():
    """Verify suspended / inactive user accounts cannot log in (403 Forbidden)."""
    res = client.post("/api/auth/login", json={"username": "suspended_user", "password": "TestPassword123!"})
    assert res.status_code == 403
    assert "inactive" in res.json()["detail"].lower()

def test_logout_endpoint():
    """Verify authenticated user can invoke logout endpoint successfully."""
    token = get_auth_token("investigator1")
    res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"

def test_bootstrap_administrator_initialized_safely():
    """Verify bootstrap administrator check returns status without exposing credentials."""
    res = client.get("/api/auth/bootstrap")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "initialized"
    assert data["bootstrap_admin"] == "admin"
    assert data["role"] == "ADMIN"
    assert "password" not in data
    assert "password_hash" not in data

# ==============================================================================
# SECTION 3: ROLE-BASED ACCESS CONTROL (4 ROLES)
# ==============================================================================

def test_rbac_case_creation_investigator_and_admin_only():
    """ADMIN & INVESTIGATOR can create cases; ANALYST & VIEWER receive 403."""
    # ADMIN
    admin_tok = get_auth_token("admin")
    res_admin = client.post("/api/cases", json={"title": "Admin Case"}, headers={"Authorization": f"Bearer {admin_tok}"})
    assert res_admin.status_code == 201

    # INVESTIGATOR
    inv_tok = get_auth_token("investigator1")
    res_inv = client.post("/api/cases", json={"title": "Investigator Case"}, headers={"Authorization": f"Bearer {inv_tok}"})
    assert res_inv.status_code == 201

    # ANALYST
    ana_tok = get_auth_token("analyst1")
    res_ana = client.post("/api/cases", json={"title": "Analyst Case"}, headers={"Authorization": f"Bearer {ana_tok}"})
    assert res_ana.status_code == 403

    # VIEWER
    view_tok = get_auth_token("viewer1")
    res_view = client.post("/api/cases", json={"title": "Viewer Case"}, headers={"Authorization": f"Bearer {view_tok}"})
    assert res_view.status_code == 403

def test_rbac_case_soft_deletion_admin_only():
    """Only ADMIN can soft-delete cases; all other roles receive 403."""
    admin_tok = get_auth_token("admin")
    case_res = client.post("/api/cases", json={"title": "Case to Delete"}, headers={"Authorization": f"Bearer {admin_tok}"})
    cid = case_res.json()["case_id"]

    for user in ["investigator1", "analyst1", "viewer1"]:
        tok = get_auth_token(user)
        res = client.delete(f"/api/cases/{cid}", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 403, f"{user} unexpectedly allowed to soft-delete case"

    del_res = client.delete(f"/api/cases/{cid}", headers={"Authorization": f"Bearer {admin_tok}"})
    assert del_res.status_code == 200

def test_rbac_evidence_upload_permissions():
    """ADMIN & INVESTIGATOR can upload evidence; ANALYST & VIEWER receive 403."""
    files = {"file": ("test.bin", io.BytesIO(b"Data"), "application/octet-stream")}

    ana_tok = get_auth_token("analyst1")
    res_ana = client.post("/api/evidence/upload", files=files, headers={"Authorization": f"Bearer {ana_tok}"})
    assert res_ana.status_code == 403

    view_tok = get_auth_token("viewer1")
    res_view = client.post("/api/evidence/upload", files=files, headers={"Authorization": f"Bearer {view_tok}"})
    assert res_view.status_code == 403

def test_rbac_blockchain_registration_permissions():
    """ADMIN & INVESTIGATOR can register evidence on blockchain; ANALYST & VIEWER receive 403."""
    payload = {"evidence_id": "EV-RBAC-BC", "hash": "a"*64}

    ana_tok = get_auth_token("analyst1")
    res_ana = client.post("/api/blockchain/register", json=payload, headers={"Authorization": f"Bearer {ana_tok}"})
    assert res_ana.status_code == 403

    view_tok = get_auth_token("viewer1")
    res_view = client.post("/api/blockchain/register", json=payload, headers={"Authorization": f"Bearer {view_tok}"})
    assert res_view.status_code == 403

def test_rbac_custody_transfer_permissions():
    """ADMIN & INVESTIGATOR can transfer custody; ANALYST & VIEWER receive 403."""
    payload = {"evidence_id": "EV-001", "new_custodian": "officer2"}

    ana_tok = get_auth_token("analyst1")
    res_ana = client.post("/api/custody/transfer", json=payload, headers={"Authorization": f"Bearer {ana_tok}"})
    assert res_ana.status_code == 403

    view_tok = get_auth_token("viewer1")
    res_view = client.post("/api/custody/transfer", json=payload, headers={"Authorization": f"Bearer {view_tok}"})
    assert res_view.status_code == 403

def test_rbac_report_generation_permissions():
    """ADMIN, INVESTIGATOR, ANALYST can generate reports; VIEWER receives 403."""
    payload = {"case_id": "CV-2026-001"}

    for user in ["admin", "investigator1", "analyst1"]:
        tok = get_auth_token(user)
        res = client.post("/api/reports/generate", json=payload, headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 200, f"{user} unexpectedly rejected from generating report"

    view_tok = get_auth_token("viewer1")
    res_view = client.post("/api/reports/generate", json=payload, headers={"Authorization": f"Bearer {view_tok}"})
    assert res_view.status_code == 403

def test_rbac_audit_all_logs_permissions():
    """ADMIN & INVESTIGATOR can query /api/audit/all; ANALYST & VIEWER receive 403."""
    for user in ["admin", "investigator1"]:
        tok = get_auth_token(user)
        res = client.get("/api/audit/all", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 200

    for user in ["analyst1", "viewer1"]:
        tok = get_auth_token(user)
        res = client.get("/api/audit/all", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 403

# ==============================================================================
# SECTION 4: OBJECT-LEVEL AUTHORIZATION & RESOURCE INTEGRITY
# ==============================================================================

def test_object_authorization_nonexistent_case_returns_404():
    """Querying non-existent case returns 404 without exposing internal state."""
    tok = get_auth_token("investigator1")
    res = client.get("/api/cases/CASE-NONEXISTENT-9999", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 404

def test_object_authorization_soft_deleted_case_inaccessible():
    """Soft-deleted cases are inaccessible via GET /api/cases/{id} (returns 404)."""
    admin_tok = get_auth_token("admin")
    case_res = client.post("/api/cases", json={"title": "To Be Deleted"}, headers={"Authorization": f"Bearer {admin_tok}"})
    cid = case_res.json()["case_id"]

    client.delete(f"/api/cases/{cid}", headers={"Authorization": f"Bearer {admin_tok}"})

    inv_tok = get_auth_token("investigator1")
    get_res = client.get(f"/api/cases/{cid}", headers={"Authorization": f"Bearer {inv_tok}"})
    assert get_res.status_code == 404

def test_object_authorization_evidence_download_nonexistent():
    """Downloading nonexistent evidence file returns 404."""
    tok = get_auth_token("investigator1")
    res = client.get("/api/evidence/download/nonexistent_file_9999.bin", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 404

def test_object_authorization_report_download_nonexistent():
    """Downloading nonexistent report file returns 404."""
    tok = get_auth_token("investigator1")
    res = client.get("/api/reports/download/nonexistent_report_9999.pdf", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 404

def test_object_authorization_evidence_immutability_delete_rejected():
    """DELETE /api/evidence/{id} must be rejected with 405/404, strictly preserving evidence."""
    admin_tok = get_auth_token("admin")
    res = client.delete("/api/evidence/EV-001", headers={"Authorization": f"Bearer {admin_tok}"})
    assert res.status_code in [404, 405]

# ==============================================================================
# SECTION 5: INPUT AND FILE SECURITY
# ==============================================================================

def test_input_path_traversal_evidence_download_blocked():
    """Directory traversal payloads on evidence download must be safely rejected (404)."""
    tok = get_auth_token("investigator1")
    for payload in ["../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "..\\windows\\win.ini"]:
        res = client.get(f"/api/evidence/download/{payload}", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code in [404, 400]

def test_input_path_traversal_report_download_blocked():
    """Directory traversal payloads on report download must be safely rejected (404)."""
    tok = get_auth_token("investigator1")
    for payload in ["../../etc/shadow", "..%2F..%2Fetc%2Fshadow", "..\\boot.ini"]:
        res = client.get(f"/api/reports/download/{payload}", headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code in [404, 400]

def test_input_oversized_upload_rejected():
    """Uploads exceeding 50MB must be rejected with 413 Request Entity Too Large."""
    tok = get_auth_token("investigator1")
    # Simulate oversized content (> 50MB) using custom BytesIO
    oversized_bytes = b"X" * (51 * 1024 * 1024)
    files = {"file": ("oversized.bin", io.BytesIO(oversized_bytes), "application/octet-stream")}
    res = client.post("/api/evidence/upload", files=files, headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 413

def test_input_unexpected_filename_characters_rejected():
    """Upload with unexpected filename characters (path separators, colons, wildcards, pipes) must be rejected with 400 Bad Request."""
    tok = get_auth_token("investigator1")
    for bad_name in ["malicious/evil.exe", "bad:name?.bin", "../traversal.bin", "pipe|command.sh", "<script>.html"]:
        files = {"file": (bad_name, io.BytesIO(b"Data"), "application/octet-stream")}
        res = client.post("/api/evidence/upload", files=files, headers={"Authorization": f"Bearer {tok}"})
        assert res.status_code == 400, f"Expected 400 for bad filename '{bad_name}', got {res.status_code}"


def test_input_mongodb_injection_operator_rejected_by_pydantic():
    """Sending MongoDB query operators like {'$gt': ''} is rejected with 422 by Pydantic schemas."""
    res = client.post("/api/auth/login", json={"username": {"$gt": ""}, "password": {"$gt": ""}})
    assert res.status_code == 422

def test_input_malformed_case_json_rejected():
    """Sending malformed case payload (missing required title) returns 422."""
    tok = get_auth_token("investigator1")
    res = client.post("/api/cases", json={"description": "Missing title"}, headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 422

# ==============================================================================
# SECTION 6: SECRETS AND SERVICE EXPOSURE
# ==============================================================================

def test_secrets_zero_credentials_leaked_in_responses():
    """Verify responses across API omit passwords, hashes, JWT secrets, and private keys."""
    tok = get_auth_token("investigator1")

    # Inspect cases response
    cases_res = client.get("/api/cases", headers={"Authorization": f"Bearer {tok}"})
    assert "password" not in cases_res.text.lower()
    assert "jwt_secret" not in cases_res.text.lower()

    # Inspect evidence response
    ev_res = client.get("/api/evidence", headers={"Authorization": f"Bearer {tok}"})
    assert "password" not in ev_res.text.lower()
    assert "private_key" not in ev_res.text.lower()

    # Inspect bootstrap response
    boot_res = client.get("/api/auth/bootstrap")
    assert "password" not in boot_res.text.lower()

def test_security_headers_present_on_responses():
    """Verify standard HTTP defensive headers are injected by middleware."""
    res = client.get("/api/health")
    assert res.status_code == 200
    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert "Strict-Transport-Security" in headers

def test_cors_preflight_restricted_to_allowed_origins():
    """Verify unauthorized origins receive no Access-Control-Allow-Origin header."""
    res = client.options(
        "/api/health",
        headers={
            "Origin": "http://evil-attacker-site.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res.headers.get("access-control-allow-origin") != "http://evil-attacker-site.com"
