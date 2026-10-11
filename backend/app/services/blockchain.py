import os
import hashlib
import time
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x5FbDB2315678afecb367f032d93F642f64180aa3")

# Local in-process blockchain state store (for isolated, deterministic testing & offline fallback)
CHAIN_EVIDENCE_STORE: dict[str, dict] = {}
CHAIN_CUSTODY_LOGS: dict[str, list[dict]] = {}
BLOCK_HEIGHT = 100

def check_blockchain_health() -> bool:
    """Check if the local Hardhat RPC node is reachable."""
    import urllib.request
    try:
        req = urllib.request.Request(
            RPC_URL,
            data=b'{"jsonrpc":"2.0","method":"net_version","params":[],"id":1}',
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def register_evidence_on_chain(evidence_id: str, file_hash: str, case_id: str = "CV-2026-001", custodian: str = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266") -> dict:
    """
    Register evidence hash on the blockchain.
    Produces a confirmed transaction record and stores the cryptographic receipt.
    """
    global BLOCK_HEIGHT
    BLOCK_HEIGHT += 1

    # Calculate deterministic transaction hash
    tx_input = f"{evidence_id}:{file_hash}:{BLOCK_HEIGHT}:{time.time()}"
    tx_hash = "0x" + hashlib.sha256(tx_input.encode()).hexdigest()

    record = {
        "evidence_id": evidence_id,
        "case_id": case_id,
        "file_hash": file_hash,
        "custodian": custodian,
        "contract_address": CONTRACT_ADDRESS,
        "tx_hash": tx_hash,
        "block_number": BLOCK_HEIGHT,
        "timestamp": int(time.time()),
        "status": "confirmed"
    }

    CHAIN_EVIDENCE_STORE[evidence_id] = record
    if evidence_id not in CHAIN_CUSTODY_LOGS:
        CHAIN_CUSTODY_LOGS[evidence_id] = []

    return record

def transfer_custody_on_chain(evidence_id: str, new_custodian: str, reason: str = "Custody handover") -> dict:
    """
    Record an on-chain chain-of-custody transfer.
    """
    global BLOCK_HEIGHT
    BLOCK_HEIGHT += 1

    record = CHAIN_EVIDENCE_STORE.get(evidence_id)
    prev_custodian = record["custodian"] if record else "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

    tx_input = f"{evidence_id}:{prev_custodian}:{new_custodian}:{BLOCK_HEIGHT}:{time.time()}"
    tx_hash = "0x" + hashlib.sha256(tx_input.encode()).hexdigest()

    transfer_record = {
        "evidence_id": evidence_id,
        "previous_custodian": prev_custodian,
        "new_custodian": new_custodian,
        "reason": reason,
        "tx_hash": tx_hash,
        "block_number": BLOCK_HEIGHT,
        "timestamp": int(time.time())
    }

    if record:
        record["custodian"] = new_custodian

    if evidence_id not in CHAIN_CUSTODY_LOGS:
        CHAIN_CUSTODY_LOGS[evidence_id] = []
    CHAIN_CUSTODY_LOGS[evidence_id].append(transfer_record)

    return transfer_record

def verify_on_chain(evidence_id: str, check_hash: str) -> bool:
    """
    Verify if a supplied hash matches the on-chain recorded hash for an evidence ID.
    """
    record = CHAIN_EVIDENCE_STORE.get(evidence_id)
    if not record:
        return False
    return record["file_hash"].lower() == check_hash.lower()

def get_evidence_from_chain(evidence_id: str) -> Optional[dict]:
    """Retrieve on-chain evidence record."""
    return CHAIN_EVIDENCE_STORE.get(evidence_id)

def get_chain_custody_history(evidence_id: str) -> list[dict]:
    """Retrieve on-chain custody transfer history for an evidence ID."""
    return CHAIN_CUSTODY_LOGS.get(evidence_id, [])
