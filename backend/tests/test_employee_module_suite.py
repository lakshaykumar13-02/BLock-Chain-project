import os
import io
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security.permissions import UserRole
from app.security.rate_limiter import login_rate_limiter
from app.services.user_service import get_account_audit_logs

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test(monkeypatch):
    login_rate_limiter.reset()
    from app.database.mongodb import db_client
    monkeypatch.setattr(db_client, "require_persistent_storage", False)

def get_token(username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Authentication failed for {username}: {res.text}"
    return res.json()["access_token"]


def test_1_employee_login_and_token_claims():
    """Verify preconfigured employee1 authenticates and receives JWT with role EMPLOYEE."""
    token = get_token("employee1", "EmployeePassword123!")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    profile = res.json()
    assert profile["username"] == "employee1"
    assert profile["role"] == "EMPLOYEE"
    assert profile["user_id"] == "USR-EMP-01"
    assert "password" not in profile
    assert "password_hash" not in profile


def test_2_admin_can_manage_employees():
    """Verify ADMIN can provision, deactivate, reactivate, and reset an Employee account."""
    admin_token = get_token("admin", "AdminPassword123!")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    emp_username = f"emp_test_{uuid.uuid4().hex[:6]}"
    emp_pwd = "SecureEmployeePass2026!"

    # 1. Admin provisions new Employee
    create_res = client.post("/api/admin/employees", headers=admin_headers, json={
        "username": emp_username,
        "password": emp_pwd,
        "full_name": "Test Forensic Assistant"
    })
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["username"] == emp_username
    assert created["role"] == "EMPLOYEE"
    assert created["is_active"] is True

    # 2. New employee authenticates successfully
    emp_token = get_token(emp_username, emp_pwd)
    assert emp_token is not None

    # 3. Admin deactivates employee
    deact_res = client.put(f"/api/admin/employees/{emp_username}/status", headers=admin_headers, json={
        "is_active": False
    })
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 4. Deactivated employee login is rejected with 403
    blocked_login = client.post("/api/auth/login", json={"username": emp_username, "password": emp_pwd})
    assert blocked_login.status_code == 403

    # 5. Prior token is revoked (401)
    revoked_check = client.get("/api/auth/me", headers={"Authorization": f"Bearer {emp_token}"})
    assert revoked_check.status_code == 401

    # 6. Admin reactivates employee
    react_res = client.put(f"/api/admin/employees/{emp_username}/status", headers=admin_headers, json={
        "is_active": True
    })
    assert react_res.status_code == 200

    # 7. Admin resets password
    new_pwd = "RotatedEmployeePass2026!"
    reset_res = client.post(f"/api/admin/employees/{emp_username}/reset-password", headers=admin_headers, json={
        "new_password": new_pwd
    })
    assert reset_res.status_code == 200

    # 8. Old password fails; new password succeeds
    assert client.post("/api/auth/login", json={"username": emp_username, "password": emp_pwd}).status_code == 401
    assert client.post("/api/auth/login", json={"username": emp_username, "password": new_pwd}).status_code == 200


def test_3_super_admin_strictly_denied_employee_management():
    """Verify SUPER_ADMIN cannot manage employees (strict separation of concerns)."""
    sa_token = get_token("superadmin", "SuperAdminDev2026!")
    sa_headers = {"Authorization": f"Bearer {sa_token}"}

    # Super Admin attempting to list employees receives 403
    res_list = client.get("/api/admin/employees", headers=sa_headers)
    assert res_list.status_code == 403
    assert "SUPER_ADMIN" in res_list.json()["detail"]

    # Super Admin attempting to create employee receives 403
    res_create = client.post("/api/admin/employees", headers=sa_headers, json={
        "username": "rogue_emp",
        "password": "Password123!"
    })
    assert res_create.status_code == 403


def test_4_investigator_strictly_denied_employee_management():
    """Verify INVESTIGATOR cannot provision or manage employee accounts."""
    inv_token = get_token("investigator1", "TestPassword123!")
    inv_headers = {"Authorization": f"Bearer {inv_token}"}

    res = client.get("/api/admin/employees", headers=inv_headers)
    assert res.status_code == 403
    assert "INVESTIGATOR" in res.json()["detail"]


def test_5_employee_strictly_denied_super_admin_and_admin_routes():
    """Verify EMPLOYEE receives 403 Forbidden on all platform governance and admin routes."""
    emp_token = get_token("employee1", "EmployeePassword123!")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # Super Admin platform endpoints
    assert client.get("/api/superadmin/summary", headers=emp_headers).status_code == 403
    assert client.get("/api/superadmin/admins", headers=emp_headers).status_code == 403
    assert client.get("/api/superadmin/audit-logs", headers=emp_headers).status_code == 403

    # Admin employee management endpoints
    assert client.get("/api/admin/employees", headers=emp_headers).status_code == 403
    assert client.post("/api/admin/employees", headers=emp_headers, json={"username": "a", "password": "b"}).status_code == 403


def test_6_employee_strictly_denied_forensic_state_mutations():
    """Verify EMPLOYEE is strictly denied all case, evidence, blockchain, and custody mutations."""
    emp_token = get_token("employee1", "EmployeePassword123!")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 1. Create Case
    res_case = client.post("/api/cases", headers=emp_headers, json={"title": "Rogue Case"})
    assert res_case.status_code == 403
    assert "EMPLOYEE" in res_case.json()["detail"]

    # 2. Soft-delete Case
    res_del_case = client.delete("/api/cases/CASE-0001", headers=emp_headers)
    assert res_del_case.status_code == 403

    # 3. Ingest Evidence
    files = {"file": ("test.bin", io.BytesIO(b"Data"), "application/octet-stream")}
    res_ev = client.post("/api/evidence/upload", headers=emp_headers, files=files)
    assert res_ev.status_code == 403

    # 4. Register On-Chain
    res_bc = client.post("/api/blockchain/register", headers=emp_headers, json={"evidence_id": "EV-001", "hash": "a"*64})
    assert res_bc.status_code == 403

    # 5. Transfer Custody
    res_cust = client.post("/api/custody/transfer", headers=emp_headers, json={"evidence_id": "EV-001", "new_custodian": "officer2"})
    assert res_cust.status_code == 403

    # 6. Generate Forensic Report
    res_rep = client.post("/api/reports/generate", headers=emp_headers, json={"case_id": "CV-2026-001"})
    assert res_rep.status_code == 403

    # 7. Recovery consistency report
    res_rec = client.get("/api/recovery/consistency-report", headers=emp_headers)
    assert res_rec.status_code == 403


def test_7_task_dispatch_and_employee_progress_update():
    """Verify ADMIN can dispatch task, and assigned EMPLOYEE can update work progress."""
    admin_token = get_token("admin", "AdminPassword123!")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    emp_token = get_token("employee1", "EmployeePassword123!")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 1. Admin dispatches task
    dispatch_res = client.post("/api/tasks", headers=admin_headers, json={
        "title": "Verify Disk Artifacts",
        "case_id": "CV-2026-001",
        "permitted_evidence_ids": ["EV-001"],
        "assigned_to_username": "employee1",
        "priority": "HIGH",
        "description": "Cross-check SHA-256 against baseline"
    })
    assert dispatch_res.status_code == 201
    task = dispatch_res.json()
    task_id = task["task_id"]
    assert task["assigned_to_username"] == "employee1"
    assert task["status"] == "ASSIGNED"

    # 2. Employee views assigned tasks
    my_tasks_res = client.get("/api/tasks/my-tasks", headers=emp_headers)
    assert my_tasks_res.status_code == 200
    my_tasks = my_tasks_res.json()
    assert any(t["task_id"] == task_id for t in my_tasks)

    # 3. Employee updates progress
    prog_res = client.put(f"/api/tasks/{task_id}/progress", headers=emp_headers, json={
        "status": "IN_PROGRESS",
        "progress_percent": 60,
        "note": "Completed disk hash verification"
    })
    assert prog_res.status_code == 200
    updated = prog_res.json()
    assert updated["status"] == "IN_PROGRESS"
    assert updated["progress_percent"] == 60
    assert len(updated["activity_log"]) >= 2


def test_8_employee_cannot_view_or_update_other_employees_tasks():
    """Verify employee cannot view or update tasks assigned to a different employee."""
    admin_token = get_token("admin", "AdminPassword123!")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    other_emp = f"other_emp_{uuid.uuid4().hex[:5]}"
    client.post("/api/admin/employees", headers=admin_headers, json={
        "username": other_emp,
        "password": "Password123!"
    })

    # Dispatch task to other employee
    task_res = client.post("/api/tasks", headers=admin_headers, json={
        "title": "Confidential Task",
        "case_id": "CV-CONFIDENTIAL",
        "assigned_to_username": other_emp
    })
    task_id = task_res.json()["task_id"]

    # employee1 attempts to view other employee's task -> 403 Forbidden
    emp1_token = get_token("employee1", "EmployeePassword123!")
    emp1_headers = {"Authorization": f"Bearer {emp1_token}"}

    view_res = client.get(f"/api/tasks/{task_id}", headers=emp1_headers)
    assert view_res.status_code == 403

    # employee1 attempts to update other employee's task -> 403 Forbidden
    update_res = client.put(f"/api/tasks/{task_id}/progress", headers=emp1_headers, json={
        "status": "COMPLETED",
        "progress_percent": 100
    })
    assert update_res.status_code == 403


def test_9_employee_scoped_case_and_evidence_access():
    """Verify employee can access assigned cases/evidence, and receives 403 on unassigned items."""
    admin_token = get_token("admin", "AdminPassword123!")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Ensure assigned case CV-2026-001 exists
    client.post("/api/cases", headers=admin_headers, json={
        "case_id": "CV-2026-001",
        "title": "Assigned Operation Case"
    })

    # Create unassigned case as admin
    unassigned_cid = f"CV-UNASSIGNED-{uuid.uuid4().hex[:4].upper()}"
    client.post("/api/cases", headers=admin_headers, json={
        "case_id": unassigned_cid,
        "title": "Restricted Unassigned Case"
    })

    emp_token = get_token("employee1", "EmployeePassword123!")
    emp_headers = {"Authorization": f"Bearer {emp_token}"}

    # 1. Employee query for unassigned case returns 403 Forbidden
    unassigned_res = client.get(f"/api/cases/{unassigned_cid}", headers=emp_headers)
    assert unassigned_res.status_code == 403
    assert "not assigned" in unassigned_res.json()["detail"].lower()

    # 2. Employee query for assigned case returns 200 OK
    assigned_res = client.get("/api/cases/CV-2026-001", headers=emp_headers)
    assert assigned_res.status_code == 200

    # 3. Employee query for unassigned evidence returns 403 Forbidden
    unassigned_ev_res = client.get("/api/evidence/EV-UNASSIGNED-999", headers=emp_headers)
    assert unassigned_ev_res.status_code == 403

    # 4. Admin query for any case still succeeds without restriction
    admin_case_res = client.get(f"/api/cases/{unassigned_cid}", headers=admin_headers)
    assert admin_case_res.status_code == 200


def test_10_account_audit_logs_record_events_without_secrets():
    """Verify employee account actions produce immutable audit logs with zero credential leakage."""
    logs = get_account_audit_logs(limit=100)
    assert isinstance(logs, list)
    assert len(logs) > 0

    actions = [l["action"] for l in logs]
    assert any("EMPLOYEE" in a or "TASK" in a for a in actions)

    for l in logs:
        assert "password" not in l
        assert "password_hash" not in l
        assert "token" not in l


def test_11_existing_roles_rbac_regression_intact():
    """Verify that all original roles (ADMIN, INVESTIGATOR, ANALYST, VIEWER) maintain their permissions."""
    # ADMIN can create case
    admin_token = get_token("admin", "AdminPassword123!")
    r1 = client.post("/api/cases", headers={"Authorization": f"Bearer {admin_token}"}, json={"title": "Admin Regression Case"})
    assert r1.status_code == 201

    # INVESTIGATOR can create case
    inv_token = get_token("investigator1", "TestPassword123!")
    r2 = client.post("/api/cases", headers={"Authorization": f"Bearer {inv_token}"}, json={"title": "Inv Regression Case"})
    assert r2.status_code == 201

    # ANALYST can generate report
    ana_token = get_token("analyst1", "TestPassword123!")
    r3 = client.post("/api/reports/generate", headers={"Authorization": f"Bearer {ana_token}"}, json={"case_id": "CV-2026-001"})
    assert r3.status_code == 200

    # VIEWER cannot create case (403)
    view_token = get_token("viewer1", "TestPassword123!")
    r4 = client.post("/api/cases", headers={"Authorization": f"Bearer {view_token}"}, json={"title": "Viewer Case"})
    assert r4.status_code == 403
