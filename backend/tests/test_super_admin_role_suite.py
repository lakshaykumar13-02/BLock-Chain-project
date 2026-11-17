import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security.rate_limiter import login_rate_limiter
from app.services.user_service import initialize_users

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_users():
    """Ensure rate limiter and users are initialized before each test."""
    login_rate_limiter.reset()

def get_auth_token(username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]

def test_super_admin_bootstrap_and_login():
    """Verify Super Admin is provisioned via environment configuration and authenticates successfully."""
    # Ensure initialized
    sa_res = client.post("/api/auth/login", json={
        "username": "superadmin",
        "password": "SuperAdminDev2026!"
    })
    assert sa_res.status_code == 200, f"Super Admin login failed: {sa_res.text}"
    data = sa_res.json()
    assert data["role"] == "SUPER_ADMIN"
    assert "access_token" in data
    assert data["user_id"].startswith("USR-")

def test_super_admin_dashboard_summary():
    """Verify Super Admin can access platform-level account governance summary."""
    token = get_auth_token("superadmin", "SuperAdminDev2026!")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/superadmin/summary", headers=headers)
    assert res.status_code == 200
    summary = res.json()
    assert "total_admins" in summary
    assert "active_admins" in summary
    assert "platform_role" in summary
    assert summary["platform_role"] == "SUPER_ADMIN"

def test_super_admin_can_create_admin_and_new_admin_logs_in():
    """Verify Super Admin can provision a new Admin and the newly created Admin can authenticate."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    headers = {"Authorization": f"Bearer {sa_token}"}

    new_admin_username = "test_ops_admin"
    new_admin_pwd = "OpsAdminSecurePassword2026!"

    # 1. Create Admin
    create_res = client.post("/api/superadmin/admins", headers=headers, json={
        "username": new_admin_username,
        "password": new_admin_pwd,
        "full_name": "Test Operations Admin"
    })
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["username"] == new_admin_username
    assert created_data["role"] == "ADMIN"
    assert created_data["is_active"] is True
    assert "password_hash" not in created_data
    assert "password" not in created_data

    # 2. Authenticate as newly created Admin
    admin_token = get_auth_token(new_admin_username, new_admin_pwd)
    assert admin_token is not None

def test_super_admin_can_deactivate_and_reactivate_admin():
    """Verify Super Admin can toggle Admin account active state and enforce session termination."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    target_admin = "test_deact_admin"
    admin_pwd = "DeactAdminPassword2026!"

    # Create admin
    client.post("/api/superadmin/admins", headers=sa_headers, json={
        "username": target_admin,
        "password": admin_pwd
    })

    # Obtain session token before deactivation
    admin_token = get_auth_token(target_admin, admin_pwd)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Deactivate Admin
    deact_res = client.put(f"/api/superadmin/admins/{target_admin}/status", headers=sa_headers, json={
        "is_active": False
    })
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 2. Deactivated admin attempting new login must be rejected with 403
    blocked_login = client.post("/api/auth/login", json={"username": target_admin, "password": admin_pwd})
    assert blocked_login.status_code == 403
    assert "inactive" in blocked_login.json()["detail"].lower()

    # 3. Existing token must be revoked
    revoked_req = client.get("/api/cases", headers=admin_headers)
    assert revoked_req.status_code == 401

    # 4. Reactivate Admin
    react_res = client.put(f"/api/superadmin/admins/{target_admin}/status", headers=sa_headers, json={
        "is_active": True
    })
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True

    # 5. Reactivated admin can login again
    fresh_token = get_auth_token(target_admin, admin_pwd)
    assert fresh_token is not None

def test_super_admin_can_reset_admin_password():
    """Verify Super Admin can securely reset an Admin's credentials and revoke prior sessions."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    target_admin = "test_reset_admin"
    old_pwd = "OldAdminPassword2026!"
    new_pwd = "NewAdminPasswordRotated2026!"

    client.post("/api/superadmin/admins", headers=sa_headers, json={
        "username": target_admin,
        "password": old_pwd
    })
    old_token = get_auth_token(target_admin, old_pwd)
    old_headers = {"Authorization": f"Bearer {old_token}"}

    # Reset password
    reset_res = client.post(f"/api/superadmin/admins/{target_admin}/reset-password", headers=sa_headers, json={
        "new_password": new_pwd
    })
    assert reset_res.status_code == 200
    assert "password_hash" not in reset_res.text
    assert new_pwd not in reset_res.text

    # Old token is revoked
    old_token_res = client.get("/api/cases", headers=old_headers)
    assert old_token_res.status_code == 401

    # Old password fails
    failed_login = client.post("/api/auth/login", json={"username": target_admin, "password": old_pwd})
    assert failed_login.status_code == 401

    # New password succeeds
    fresh_token = get_auth_token(target_admin, new_pwd)
    assert fresh_token is not None

def test_super_admin_can_remove_admin_with_confirmation():
    """Verify Admin removal requires confirmation and permanently terminates access."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    target_admin = "test_remove_admin"
    admin_pwd = "RemoveAdminPassword2026!"

    client.post("/api/superadmin/admins", headers=sa_headers, json={
        "username": target_admin,
        "password": admin_pwd
    })

    # 1. Attempt removal without confirmation must be rejected
    unconf_res = client.delete(f"/api/superadmin/admins/{target_admin}?confirm=false", headers=sa_headers)
    assert unconf_res.status_code == 400
    assert "confirmation" in unconf_res.json()["detail"].lower()

    # 2. Confirmed removal succeeds
    del_res = client.delete(f"/api/superadmin/admins/{target_admin}?confirm=true", headers=sa_headers)
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 3. Removed user cannot authenticate
    deleted_login = client.post("/api/auth/login", json={"username": target_admin, "password": admin_pwd})
    assert deleted_login.status_code == 401

def test_admin_is_strictly_denied_super_admin_endpoints():
    """Verify ordinary Admin accounts receive HTTP 403 Forbidden on all Super Admin routes."""
    admin_token = get_auth_token("admin", "AdminPassword123!")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Summary
    res1 = client.get("/api/superadmin/summary", headers=headers)
    assert res1.status_code == 403
    assert "Role 'ADMIN' lacks permission" in res1.json()["detail"]

    # Admins list
    res2 = client.get("/api/superadmin/admins", headers=headers)
    assert res2.status_code == 403

    # Create Admin
    res3 = client.post("/api/superadmin/admins", headers=headers, json={
        "username": "hacker_admin",
        "password": "HackerPassword123!"
    })
    assert res3.status_code == 403

    # Audit logs
    res4 = client.get("/api/superadmin/audit-logs", headers=headers)
    assert res4.status_code == 403

def test_investigator_is_strictly_denied_super_admin_endpoints():
    """Verify Investigator accounts receive HTTP 403 Forbidden on all Super Admin routes."""
    inv_token = get_auth_token("investigator1", "TestPassword123!")
    headers = {"Authorization": f"Bearer {inv_token}"}

    res1 = client.get("/api/superadmin/summary", headers=headers)
    assert res1.status_code == 403
    assert "Role 'INVESTIGATOR' lacks permission" in res1.json()["detail"]

    res2 = client.post("/api/superadmin/admins", headers=headers, json={
        "username": "rogue_admin",
        "password": "RoguePassword123!"
    })
    assert res2.status_code == 403

def test_anti_lockout_super_admin_cannot_be_disabled_or_removed():
    """Verify Super Admin cannot be disabled or deleted through Admin management endpoints."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    # Attempt to deactivate Super Admin
    deact_res = client.put("/api/superadmin/admins/superadmin/status", headers=sa_headers, json={
        "is_active": False
    })
    assert deact_res.status_code == 403 or deact_res.status_code == 400

    # Attempt to delete Super Admin
    del_res = client.delete("/api/superadmin/admins/superadmin?confirm=true", headers=sa_headers)
    assert del_res.status_code == 403 or del_res.status_code == 400

def test_account_audit_logs_record_events_without_leaking_secrets():
    """Verify account management actions produce immutable audit logs without secrets."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    res = client.get("/api/superadmin/audit-logs", headers=sa_headers)
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) > 0

    # Check structure and verify zero password leaks
    for log in logs:
        assert "event_id" in log
        assert "action" in log
        assert "actor_username" in log
        assert "timestamp" in log
        assert "outcome" in log
        # Check no secret fields exist
        assert "password" not in log
        assert "password_hash" not in log
        assert "access_token" not in log

def test_super_admin_isolated_from_evidence_content():
    """Verify SUPER_ADMIN is isolated from evidence investigation routes (tenant boundary)."""
    sa_token = get_auth_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    # Attempting to delete a case requires ADMIN role
    del_res = client.delete("/api/cases/CASE-001", headers=sa_headers)
    assert del_res.status_code == 403
    assert "SUPER_ADMIN" in del_res.json()["detail"]
