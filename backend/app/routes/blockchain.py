from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional

from ..services.blockchain import (
    register_evidence_on_chain,
    get_evidence_from_chain,
    check_blockchain_health
)
from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from .evidence import EVIDENCE_STORE

router = APIRouter(prefix="/blockchain", tags=["Blockchain"])

class BlockchainRegisterRequest(BaseModel):
    evidence_id: str
    hash: str
    case_id: Optional[str] = "CV-2026-001"

@router.post("/register", status_code=status.HTTP_200_OK)
async def register_evidence(
    req: BlockchainRegisterRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """
    Register evidence cryptographic hash on the local Ethereum blockchain.
    Allowed roles: ADMIN, INVESTIGATOR.
    """
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
    """Check status and connectivity of local blockchain service. Public."""
    online = check_blockchain_health()
    return {
        "status": "online" if online else "offline",
        "rpc_url": "http://127.0.0.1:8545",
        "network": "Hardhat Local Testnet"
    }

@router.get("/evidence/{evidence_id}")
async def get_blockchain_evidence(
    evidence_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve evidence record recorded on the blockchain ledger. Allowed roles: All authenticated."""
    record = get_evidence_from_chain(evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found on blockchain")
    return record

@router.post("/reconcile/{evidence_id}", status_code=status.HTTP_200_OK)
async def reconcile_evidence(
    evidence_id: str,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """
    Reconciliation service for pending or uncertain transactions:
    Inspects on-chain state first before any action. If confirmed on-chain,
    synchronizes local database metadata without issuing redundant transactions.
    """
    chain_record = get_evidence_from_chain(evidence_id)
    if not chain_record:
        raise HTTPException(
            status_code=404,
            detail=f"Evidence {evidence_id} not found on blockchain; cannot reconcile unconfirmed record"
        )

    # Reconcile local store state
    if evidence_id in EVIDENCE_STORE:
        EVIDENCE_STORE[evidence_id]["blockchain_registered"] = True
        EVIDENCE_STORE[evidence_id]["blockchain_tx"] = chain_record["tx_hash"]
        EVIDENCE_STORE[evidence_id]["blockchain_status"] = "confirmed"

    return {
        "status": "reconciled",
        "evidence_id": evidence_id,
        "blockchain_tx": chain_record["tx_hash"],
        "block_number": chain_record.get("block_number"),
        "on_chain_hash": chain_record.get("file_hash")
    }
