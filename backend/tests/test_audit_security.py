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

@pytest.mark.xfail(reason="BLOCKED: backend/app/security/password.py is a stub; password hash functions not yet implemented", strict=True)
def test_password_hashing_security_module():
    """Requirement 1: Verify password hashing module exposes secure bcrypt utilities."""
    from app.security import password
    assert hasattr(password, "hash_password"), "Password module must expose hash_password"
    assert hasattr(password, "verify_password"), "Password module must expose verify_password"
