import pytest
import os
import uuid
from starlette.testclient import TestClient
from app.main import app
from app.security.permissions import UserRole

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def superadmin_token(client):
    sa_username = os.getenv("SUPER_ADMIN_INITIAL_USERNAME", "superadmin").strip()
    sa_password = os.getenv("SUPER_ADMIN_INITIAL_PASSWORD", "SuperAdminDev2026!")
    resp = client.post("/api/auth/login", json={"username": sa_username, "password": sa_password})
    assert resp.status_code == 200, f"Superadmin login failed: {resp.text}"
    return resp.json()["access_token"]

def test_1_distinct_persistent_user_ids_for_different_admins(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    u1 = f"admin_alpha_{uuid.uuid4().hex[:6]}"
    u2 = f"admin_beta_{uuid.uuid4().hex[:6]}"

    # Provision Admin Alpha
    r1 = client.post("/api/superadmin/admins", json={
        "username": u1,
        "password": "TestPassword123!",
        "full_name": "Officer Alpha"
    }, headers=headers)
    assert r1.status_code == 201
    d1 = r1.json()

    # Provision Admin Beta
    r2 = client.post("/api/superadmin/admins", json={
        "username": u2,
        "password": "TestPassword123!",
        "full_name": "Officer Beta"
    }, headers=headers)
    assert r2.status_code == 201
    d2 = r2.json()

    # Verify both have distinct, non-empty user IDs
    assert d1["user_id"] != d2["user_id"]
    assert d1["username"] == u1
    assert d2["username"] == u2
    assert d1["display_name"] == "Officer Alpha"
    assert d2["display_name"] == "Officer Beta"

def test_2_duplicate_username_rejected_case_insensitive(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    base_uname = f"unique_adm_{uuid.uuid4().hex[:5]}"

    # First creation succeeds
    r1 = client.post("/api/superadmin/admins", json={
        "username": base_uname,
        "password": "TestPassword123!",
        "full_name": "First Account"
    }, headers=headers)
    assert r1.status_code == 201

    # Exact duplicate rejected with 409
    r2 = client.post("/api/superadmin/admins", json={
        "username": base_uname,
        "password": "AnotherPassword123!",
        "full_name": "Duplicate Exact"
    }, headers=headers)
    assert r2.status_code == 409

    # Case-insensitive duplicate rejected with 409
    r3 = client.post("/api/superadmin/admins", json={
        "username": base_uname.upper(),
        "password": "AnotherPassword123!",
        "full_name": "Duplicate Upper"
    }, headers=headers)
    assert r3.status_code == 409

def test_3_creating_new_admin_does_not_overwrite_existing(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    u_first = f"admin_orig_{uuid.uuid4().hex[:5]}"
    u_second = f"admin_subseq_{uuid.uuid4().hex[:5]}"

    r1 = client.post("/api/superadmin/admins", json={
        "username": u_first,
        "password": "TestPassword123!",
        "full_name": "Original Officer"
    }, headers=headers)
    assert r1.status_code == 201
    orig_id = r1.json()["user_id"]

    r2 = client.post("/api/superadmin/admins", json={
        "username": u_second,
        "password": "TestPassword123!",
        "full_name": "Subsequent Officer"
    }, headers=headers)
    assert r2.status_code == 201

    # Login as first user and verify their profile is intact
    login1 = client.post("/api/auth/login", json={"username": u_first, "password": "TestPassword123!"})
    assert login1.status_code == 200
    data1 = login1.json()
    assert data1["user_id"] == orig_id
    assert data1["username"] == u_first
    assert data1["display_name"] == "Original Officer"

def test_4_each_admin_sees_their_own_display_name_after_login(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    uname = f"admin_named_{uuid.uuid4().hex[:5]}"
    display_title = "Detective Alex Murphy (Robotics Unit)"

    # Create admin with specific display name
    create_resp = client.post("/api/superadmin/admins", json={
        "username": uname,
        "password": "TestPassword123!",
        "display_name": display_title
    }, headers=headers)
    assert create_resp.status_code == 201

    # Login as this admin
    login_resp = client.post("/api/auth/login", json={"username": uname, "password": "TestPassword123!"})
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["display_name"] == display_title
    assert login_data["username"] == uname

    # Query /api/auth/me using their access token
    token = login_data["access_token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["display_name"] == display_title
    assert me_data["username"] == uname
    assert me_data["user_id"] == login_data["user_id"]

def test_5_profile_update_workflow_refreshes_display_name(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    uname = f"admin_updater_{uuid.uuid4().hex[:5]}"

    create_resp = client.post("/api/superadmin/admins", json={
        "username": uname,
        "password": "TestPassword123!",
        "full_name": "Initial Name"
    }, headers=headers)
    assert create_resp.status_code == 201

    login_resp = client.post("/api/auth/login", json={"username": uname, "password": "TestPassword123!"})
    token = login_resp.json()["access_token"]

    # Call PUT /api/auth/profile to update display name
    new_name = "Inspector Jane Doe (Forensics)"
    put_resp = client.put("/api/auth/profile", json={"display_name": new_name}, headers={"Authorization": f"Bearer {token}"})
    assert put_resp.status_code == 200
    assert put_resp.json()["display_name"] == new_name

    # Check GET /api/auth/me immediately reflects updated name
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["display_name"] == new_name

def test_6_account_switching_no_data_leakage(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    u_a = f"adm_a_{uuid.uuid4().hex[:5]}"
    u_b = f"adm_b_{uuid.uuid4().hex[:5]}"

    client.post("/api/superadmin/admins", json={"username": u_a, "password": "PasswordA123!", "full_name": "Alice Admin"}, headers=headers)
    client.post("/api/superadmin/admins", json={"username": u_b, "password": "PasswordB123!", "full_name": "Bob Admin"}, headers=headers)

    # Login as User A
    resp_a = client.post("/api/auth/login", json={"username": u_a, "password": "PasswordA123!"})
    token_a = resp_a.json()["access_token"]
    me_a = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert me_a["username"] == u_a
    assert me_a["display_name"] == "Alice Admin"

    # User A logs out
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token_a}"})

    # Login as User B
    resp_b = client.post("/api/auth/login", json={"username": u_b, "password": "PasswordB123!"})
    token_b = resp_b.json()["access_token"]
    me_b = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert me_b["username"] == u_b
    assert me_b["display_name"] == "Bob Admin"

    # Verify no overlap between A and B
    assert me_a["user_id"] != me_b["user_id"]
    assert me_a["username"] != me_b["username"]
    assert me_a["display_name"] != me_b["display_name"]

def test_7_superadmin_directory_shows_correct_name_and_status(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    dir_resp = client.get("/api/superadmin/admins", headers=headers)
    assert dir_resp.status_code == 200
    admins = dir_resp.json()
    assert isinstance(admins, list)
    assert len(admins) >= 2

    for a in admins:
        assert "user_id" in a
        assert "username" in a
        assert "display_name" in a
        assert "is_active" in a
        assert "password_hash" not in a

def test_8_changing_status_of_one_admin_isolates_others(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    u_target = f"adm_target_{uuid.uuid4().hex[:5]}"
    u_other = f"adm_other_{uuid.uuid4().hex[:5]}"

    client.post("/api/superadmin/admins", json={"username": u_target, "password": "TestPassword123!", "full_name": "Target Admin"}, headers=headers)
    client.post("/api/superadmin/admins", json={"username": u_other, "password": "TestPassword123!", "full_name": "Other Admin"}, headers=headers)

    # Deactivate Target Admin
    toggle_resp = client.put(f"/api/superadmin/admins/{u_target}/status", json={"is_active": False}, headers=headers)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False

    # Target admin login fails with 403
    t_login = client.post("/api/auth/login", json={"username": u_target, "password": "TestPassword123!"})
    assert t_login.status_code == 403

    # Other admin is unaffected and can still login
    o_login = client.post("/api/auth/login", json={"username": u_other, "password": "TestPassword123!"})
    assert o_login.status_code == 200
    assert o_login.json()["display_name"] == "Other Admin"

def test_9_zero_secrets_or_hashes_exposed_in_api_responses(client, superadmin_token):
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. Login response
    l_resp = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    l_data = l_resp.json()
    assert "password_hash" not in l_data
    assert "password" not in l_data

    # 2. /me profile response
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {l_data['access_token']}"})
    me_data = me_resp.json()
    assert "password_hash" not in me_data
    assert "password" not in me_data

    # 3. Superadmin directory
    sa_dir = client.get("/api/superadmin/admins", headers=headers).json()
    for item in sa_dir:
        assert "password_hash" not in item
        assert "password" not in item

def test_10_admin_and_investigator_forbidden_from_superadmin(client):
    # Admin login
    r_adm = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    adm_token = r_adm.json()["access_token"]

    # Investigator login
    r_inv = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    inv_token = r_inv.json()["access_token"]

    # Both must receive 403 on superadmin endpoints
    for token in (adm_token, inv_token):
        h = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/superadmin/admins", headers=h).status_code == 403
        assert client.get("/api/superadmin/summary", headers=h).status_code == 403
        assert client.post("/api/superadmin/admins", json={"username": "hacker", "password": "pwd"}, headers=h).status_code == 403

def test_11_operational_workflows_preserved(client):
    r_adm = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    adm_token = r_adm.json()["access_token"]
    h = {"Authorization": f"Bearer {adm_token}"}

    # Case listing works
    cases_resp = client.get("/api/cases", headers=h)
    assert cases_resp.status_code == 200

    # Evidence listing works
    ev_resp = client.get("/api/evidence", headers=h)
    assert ev_resp.status_code == 200
