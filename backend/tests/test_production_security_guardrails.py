import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.security.rate_limiter import login_rate_limiter

client = TestClient(app)

def test_defensive_security_headers_present():
    """Verify production security headers are attached to all API responses."""
    res = client.get("/api/health")
    assert res.status_code == 200
    headers = res.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-xss-protection") == "1; mode=block"
    assert "max-age=31536000" in headers.get("strict-transport-security", "")
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in headers.get("content-security-policy", "")

def test_login_authentication_valid_credentials():
    """Verify Admin and Investigator authentications succeed and yield valid JWTs."""
    login_rate_limiter.reset()

    # Admin
    admin_res = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    assert admin_res.status_code == 200
    admin_data = admin_res.json()
    assert admin_data["role"] == "ADMIN"
    assert "access_token" in admin_data

    # Investigator
    inv_res = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    assert inv_res.status_code == 200
    inv_data = inv_res.json()
    assert inv_data["role"] == "INVESTIGATOR"
    assert "access_token" in inv_data

def test_login_rate_limiting_brute_force_protection():
    """Verify rate limiter blocks credential-stuffing after 5 consecutive failures."""
    login_rate_limiter.reset()
    target_user = "test_brute_target"

    for attempt in range(5):
        res = client.post("/api/auth/login", json={"username": target_user, "password": f"WrongPwd{attempt}"})
        assert res.status_code == 401

    # 6th attempt must trigger HTTP 429 Too Many Requests
    blocked_res = client.post("/api/auth/login", json={"username": target_user, "password": "WrongPassword6"})
    assert blocked_res.status_code == 429
    assert "Too many failed login attempts" in blocked_res.json()["detail"]
    assert "retry-after" in blocked_res.headers

    # Reset for other tests
    login_rate_limiter.reset()

def test_path_traversal_download_protection():
    """Verify path traversal vectors on evidence download are blocked."""
    # Obtain admin token for authentication
    login_rate_limiter.reset()
    auth_res = client.post("/api/auth/login", json={"username": "admin", "password": "AdminPassword123!"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for traversal in ["../../boot.ini", "..%2f..%2fetc%2fpasswd", "evidence.bin%00.txt"]:
        res = client.get(f"/api/evidence/download/{traversal}", headers=headers)
        assert res.status_code == 404, f"Traversal {traversal} was not rejected with 404!"

def test_investigator_forbidden_from_admin_actions():
    """Verify investigator token is strictly blocked from ADMIN-only routes."""
    login_rate_limiter.reset()
    auth_res = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    token = auth_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Soft-delete case (ADMIN only)
    del_res = client.delete("/api/cases/CASE-0001", headers=headers)
    assert del_res.status_code == 403
    assert "Role 'INVESTIGATOR' lacks permission" in del_res.json()["detail"]

    # 2. System consistency report (ADMIN only)
    rec_res = client.get("/api/recovery/consistency-report", headers=headers)
    assert rec_res.status_code == 403
    assert "Role 'INVESTIGATOR' lacks permission" in rec_res.json()["detail"]

def test_client_ip_proxy_spoofing_protection():
    """Verify that untrusted direct clients cannot spoof X-Forwarded-For to bypass rate limits."""
    from app.security.rate_limiter import get_client_ip

    class DummyClient:
        def __init__(self, host):
            self.host = host

    class DummyRequest:
        def __init__(self, host, headers=None):
            self.client = DummyClient(host)
            self.headers = headers or {}

    # Case 1: Untrusted external client attempts to spoof X-Forwarded-For
    untrusted_req = DummyRequest(host="203.0.113.50", headers={"X-Forwarded-For": "198.51.100.1"})
    # Only 127.0.0.1 and ::1 are trusted proxies
    resolved_ip = get_client_ip(untrusted_req, trusted_proxies_str="127.0.0.1,::1")
    assert resolved_ip == "203.0.113.50", "Spoofed X-Forwarded-For from untrusted IP must be rejected!"

    # Case 2: Trusted reverse proxy sends forwarded client IP
    trusted_req = DummyRequest(host="10.0.0.1", headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1"})
    resolved_ip = get_client_ip(trusted_req, trusted_proxies_str="10.0.0.1")
    assert resolved_ip == "198.51.100.1", "Forwarded IP from trusted proxy must be accepted!"

def test_production_preflight_validation_failures(monkeypatch):
    """Verify validate_production_preflight_config fails fast on insecure configurations."""
    from app.main import validate_production_preflight_config

    # Set ENVIRONMENT=production
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "super_secret_jwt_key_chainvault_staging_32_chars_long")
    monkeypatch.setenv("ADMIN_INITIAL_PASSWORD", "SuperSecureProdAdminPassword2026!")
    monkeypatch.setenv("REQUIRE_PERSISTENT_STORAGE", "true")
    monkeypatch.setenv("DATABASE_BACKEND", "firestore")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "chainvault-prod")
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "https://sepolia.infura.io/v3/real_key")
    monkeypatch.setenv("BLOCKCHAIN_CHAIN_ID", "11155111")
    monkeypatch.setenv("CONTRACT_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("ALLOW_LOCAL_QR_LINKS", "false")
    monkeypatch.setenv("PUBLIC_VERIFICATION_URL_BASE", "https://chainvault.example.com")
    monkeypatch.setenv("CORS_ORIGINS", "https://chainvault.example.com")

    # Happy path: should not raise
    validate_production_preflight_config()

    # Insecure 1: Local Hardhat chain ID 31337 in production
    monkeypatch.setenv("BLOCKCHAIN_CHAIN_ID", "31337")
    with pytest.raises(RuntimeError, match="cannot target local Hardhat testnet"):
        validate_production_preflight_config()
    monkeypatch.setenv("BLOCKCHAIN_CHAIN_ID", "11155111")

    # Insecure 2: FIRESTORE_EMULATOR_HOST active in production
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    with pytest.raises(RuntimeError, match="cannot target FIRESTORE_EMULATOR_HOST"):
        validate_production_preflight_config()
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)

    # Insecure 3: Wildcard CORS origin in production
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="forbids wildcard"):
        validate_production_preflight_config()
    monkeypatch.setenv("CORS_ORIGINS", "https://chainvault.example.com")

    # Insecure 4: Non-HTTPS verification base URL
    monkeypatch.setenv("PUBLIC_VERIFICATION_URL_BASE", "http://insecure-site.com")
    with pytest.raises(RuntimeError, match="start with 'https://'"):
        validate_production_preflight_config()

