from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_cors_frontend_port_allowed():
    """Verify that requests from the authorized frontend port (5500) receive CORS headers."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://127.0.0.1:5500",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
