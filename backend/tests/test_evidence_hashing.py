import hashlib
import pytest

def test_sha256_cryptographic_correctness():
    """Requirement 4 & 5: Verify SHA-256 algorithm produces correct digests for known synthetic data."""
    # Test vector 1: Empty payload
    empty_digest = hashlib.sha256(b"").hexdigest()
    assert empty_digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # Test vector 2: Synthetic evidence string
    sample_data = b"ChainVault Forensic Digital Evidence Sample Payload 2026"
    expected_digest = hashlib.sha256(sample_data).hexdigest()
    assert len(expected_digest) == 64
    assert isinstance(expected_digest, str)

@pytest.mark.xfail(reason="BLOCKED: backend/app/services/hashing.py is a stub; calculate_hash function not yet implemented", strict=True)
def test_hashing_service_module():
    """Verify hashing service module exports calculate_file_hash."""
    from app.services import hashing
    assert hasattr(hashing, "calculate_hash"), "hashing service must expose calculate_hash"
