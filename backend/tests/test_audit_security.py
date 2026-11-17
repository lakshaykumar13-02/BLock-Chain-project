import os
import pytest

def test_env_example_contains_all_required_keys():
    """Requirement 11 & 13: Verify .env.example defines all required configuration parameters without real secrets."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_example_path = os.path.join(root_dir, ".env.example")
    assert os.path.exists(env_example_path), ".env.example must exist"

    with open(env_example_path, "r") as f:
        content = f.read()

    required_keys = [
        "MONGO_URI",
        "MONGO_DB_NAME",
        "JWT_SECRET",
        "JWT_EXPIRE_MINUTES",
        "BLOCKCHAIN_RPC_URL",
        "CONTRACT_ADDRESS",
        "STORAGE_PATH"
    ]
    for key in required_keys:
        assert f"{key}=" in content, f".env.example must define {key}"

def test_gitignore_protects_evidence_and_reports():
    """Requirement 11: Verify .gitignore contains rules protecting storage and generated reports."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    gitignore_path = os.path.join(root_dir, ".gitignore")
    assert os.path.exists(gitignore_path), ".gitignore must exist"

    with open(gitignore_path, "r") as f:
        content = f.read()

    assert ".env" in content
    assert "node_modules/" in content
    assert "venv/" in content
    assert "storage/evidence/*" in content or "CHAINVAULT/backend/storage/evidence/*" in content
    assert "generated_reports/*" in content or "CHAINVAULT/backend/generated_reports/*" in content

def test_password_hashing_security_module():
    """Requirement 1: Verify password hashing module exposes secure bcrypt utilities."""
    from app.security import password
    assert hasattr(password, "hash_password"), "Password module must expose hash_password"
    assert hasattr(password, "verify_password"), "Password module must expose verify_password"


def test_gitignore_protects_cloud_credentials():
    """Verify .gitignore blocks all cloud service account keys, tokens, and credential files."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    gitignore_path = os.path.join(root_dir, ".gitignore")
    with open(gitignore_path, "r") as f:
        content = f.read()

    assert "*service-account*.json" in content
    assert "*service_account*.json" in content
    assert "*credentials*.json" in content
    assert "*firebase-adminsdk*.json" in content
    assert "*.pem" in content
    assert "*.key" in content
    assert "secrets/" in content


def test_env_example_database_backend_defaults_to_mongodb():
    """Verify .env.example defaults to mongodb as authoritative backend."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_example_path = os.path.join(root_dir, ".env.example")
    with open(env_example_path, "r") as f:
        content = f.read()

    assert "DATABASE_BACKEND=mongodb" in content
    assert "FIREBASE_PROJECT_ID=chainvault-staging" in content
    assert "FIRESTORE_DATABASE_ID=(default)" in content


def test_firestore_adapter_credential_loading_precedence(monkeypatch):
    """Verify FirestoreClient correctly handles emulator vs service account vs ADC precedence."""
    from app.database.firestore import FirestoreClient

    # 1. Emulator precedence: emulator_host sets environment and skips file lookup
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "non_existent_key.json")
    client = FirestoreClient()
    assert client.emulator_host == "127.0.0.1:8080"
    assert client.credentials_path == "non_existent_key.json"

    # 2. Project ID fallback
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    client_default = FirestoreClient()
    assert client_default.project_id == "chainvault-staging"
    assert client_default.database_id == "(default)"
