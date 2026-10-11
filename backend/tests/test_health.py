from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    """Verify that the FastAPI health endpoint returns 200 and expected payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ChainVault API"

def test_nonexistent_endpoint_returns_404():
    """Verify that unmapped routes return 404 Not Found."""
    response = client.get("/api/nonexistent")
    assert response.status_code == 404
