from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from ..services.blockchain import (
    register_evidence_on_chain,
    get_evidence_from_chain,
    check_blockchain_health
)
from .evidence import EVIDENCE_STORE

router = APIRouter(prefix="/blockchain", tags=["Blockchain"])

class BlockchainRegisterRequest(BaseModel):
    evidence_id: str
    hash: str
    case_id: Optional[str] = "CV-2026-001"

@router.post("/register", status_code=status.HTTP_200_OK)
async def register_evidence(req: BlockchainRegisterRequest):
    """Register evidence cryptographic hash on the local Ethereum blockchain."""
    receipt = register_evidence_on_chain(
        evidence_id=req.evidence_id,
        file_hash=req.hash,
        case_id=req.case_id or "CV-2026-001"
    )

    # Update metadata in evidence store if present
    if req.evidence_id in EVIDENCE_STORE:
        EVIDENCE_STORE[req.evidence_id]["blockchain_registered"] = True
        EVIDENCE_STORE[req.evidence_id]["blockchain_tx"] = receipt["tx_hash"]

    return {
        "status": "success",
        "message": f"Evidence {req.evidence_id} registered on blockchain",
        "tx_hash": receipt["tx_hash"],
        "block_number": receipt["block_number"],
        "receipt": receipt
    }

@router.get("/status")
async def blockchain_status():
    """Check status and connectivity of local blockchain service."""
    online = check_blockchain_health()
    return {
        "status": "online" if online else "offline",
        "rpc_url": "http://127.0.0.1:8545",
        "network": "Hardhat Local Testnet"
    }

@router.get("/evidence/{evidence_id}")
async def get_blockchain_evidence(evidence_id: str):
    """Retrieve evidence record recorded on the blockchain ledger."""
    record = get_evidence_from_chain(evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found on blockchain")
    return record
