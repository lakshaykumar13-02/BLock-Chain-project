import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_no_evidence_delete_endpoint():
    response = client.delete("/api/evidence/123")
    # Deletion must be rejected - either 404 (Not Found) or 405 (Method Not Allowed)
    assert response.status_code in [404, 405]

def test_no_hardcoded_env_file_committed():
    """Requirement 3.G: Secrets outside source control."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_file = os.path.join(root_dir, ".env")
    assert not os.path.exists(env_file), "Live .env must not exist in version control"

def test_evidence_storage_directory_traversal_protection():
    """Requirement 3.G: Path traversal protection on storage endpoints."""
    malicious_path = "../../../etc/passwd"
    response = client.get(f"/api/evidence/download/{malicious_path}")
    assert response.status_code == 404
