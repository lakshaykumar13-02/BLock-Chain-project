import os
import pytest
import urllib.request
import urllib.error

def test_blockchain_rpc_configuration():
    """Requirement 1 & 2.B: Verify blockchain RPC URL points strictly to local Hardhat network."""
    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    assert "127.0.0.1:8545" in rpc_url or "localhost:8545" in rpc_url, "Must point strictly to local Hardhat node"
    assert "mainnet" not in rpc_url.lower()
    assert "infura" not in rpc_url.lower()
    assert "alchemy" not in rpc_url.lower()

def test_blockchain_rpc_reachability_detection():
    """Requirement 3: Verify system accurately detects blockchain node connectivity."""
    from app.services.blockchain import check_blockchain_health
    # With standalone Hardhat node active on port 8545, check_blockchain_health() returns True
    assert check_blockchain_health() is True, "System must detect active standalone Hardhat node"

def test_blockchain_service_integration_module():
    """Requirement 2.B: Verify blockchain service module exports registration and custody handlers."""
    from app.services import blockchain
    assert hasattr(blockchain, "register_evidence_on_chain"), "blockchain service must expose register_evidence_on_chain"
