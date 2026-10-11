import os
import shutil
import tempfile
import pytest
from pathlib import Path

# Ensure tests strictly target chainvault_test
os.environ["MONGO_DB_NAME"] = "chainvault_test"

@pytest.fixture(autouse=True)
def enforce_test_database_isolation():
    """Guarantee that tests never target the development database."""
    assert os.getenv("MONGO_DB_NAME") == "chainvault_test", (
        "CRITICAL SAFETY VIOLATION: Test suite executed with non-test database! "
        f"Expected 'chainvault_test', got '{os.getenv('MONGO_DB_NAME')}'."
    )
    yield

@pytest.fixture
def isolated_storage_dir(monkeypatch, tmp_path):
    """Provide an isolated temporary directory for synthetic evidence files."""
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("STORAGE_PATH", str(evidence_dir))
    yield evidence_dir

@pytest.fixture
def isolated_reports_dir(monkeypatch, tmp_path):
    """Provide an isolated temporary directory for generated forensic reports."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPORTS_PATH", str(reports_dir))
    yield reports_dir
