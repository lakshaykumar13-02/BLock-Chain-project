import os
import re
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_frontend_api_base_url_matches_backend():
    """Requirement 2.D: Verify frontend api.js base URL aligns with FastAPI backend routing."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    api_js_path = os.path.join(root_dir, "frontend", "js", "api.js")
    assert os.path.exists(api_js_path), "frontend/js/api.js must exist"

    with open(api_js_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "http://localhost:8000/api" in content or "http://127.0.0.1:8000/api" in content

def test_zero_secrets_or_private_keys_in_frontend_assets():
    """Requirement 2.D: Guarantee private keys, passwords, and JWT secrets are never embedded in frontend code."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    frontend_dir = os.path.join(root_dir, "frontend")

    # Scan all frontend files (.html, .js, .css)
    for root, _, files in os.walk(frontend_dir):
        for file in files:
            file_path = os.path.join(root, file)
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Check for hex private keys (64 hex characters)
            assert not re.search(r'0x[a-fA-F0-9]{64}', content), f"Private key pattern detected in {file}"
            # Check for hardcoded JWT secrets
            assert "your_super_secret_key" not in content, f"JWT secret leaked into {file}"

def test_frontend_api_health_endpoint_integration():
    """Requirement 2.D: Verify the health endpoint consumed by frontend returns HTTP 200."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ChainVault API"}
