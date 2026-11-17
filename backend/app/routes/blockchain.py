from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional

from ..services.blockchain import (
    register_evidence_on_chain,
    get_evidence_from_chain,
    check_blockchain_health,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS
)
from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..database.mongodb import db_client
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
    try:
        receipt = register_evidence_on_chain(
            evidence_id=req.evidence_id,
            file_hash=req.hash,
            case_id=req.case_id or "CV-2026-001"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )

    # Update metadata in evidence store if present
    if req.evidence_id in EVIDENCE_STORE:
        EVIDENCE_STORE[req.evidence_id]["blockchain_registered"] = True
        EVIDENCE_STORE[req.evidence_id]["blockchain_tx"] = receipt["tx_hash"]
        EVIDENCE_STORE[req.evidence_id]["block_number"] = receipt.get("block_number")

    # Update persistent database
    if db_client.is_connected():
        try:
            await db_client.evidence.update_one(
                {"evidence_id": req.evidence_id},
                {"$set": {
                    "blockchain_registered": True,
                    "blockchain_tx": receipt["tx_hash"],
                    "block_number": receipt.get("block_number"),
                    "contract_address": receipt.get("contract_address")
                }}
            )
            await db_client.blockchain_checkpoints.update_one(
                {"evidence_id": req.evidence_id},
                {"$set": {
                    "checkpoint_id": f"CHK-{req.evidence_id}",
                    "evidence_id": req.evidence_id,
                    "file_hash": req.hash,
                    "tx_hash": receipt["tx_hash"],
                    "block_number": receipt.get("block_number"),
                    "contract_address": receipt.get("contract_address"),
                    "chain_id": receipt.get("chain_id")
                }},
                upsert=True
            )
        except Exception:
            pass

    # Record tamper-evident custody audit event for blockchain anchoring
    from ..services.audit_trail import record_custody_event
    await record_custody_event(
        evidence_id=req.evidence_id,
        action="BLOCKCHAIN_REGISTRATION",
        actor_id=current_user.get("username", "investigator1"),
        case_id=req.case_id or "CV-2026-001",
        details={
            "file_hash": req.hash,
            "tx_hash": receipt["tx_hash"],
            "block_number": receipt.get("block_number"),
            "contract_address": receipt.get("contract_address")
        },
        anchor_reference=receipt["tx_hash"]
    )

    return {
        "status": "success",
        "message": f"Evidence {req.evidence_id} registered on blockchain",
        "tx_hash": receipt["tx_hash"],
        "block_number": receipt["block_number"],
        "receipt": receipt
    }

@router.get("/status")
async def blockchain_status():
    """Check status and connectivity of blockchain service. Public."""
    online = check_blockchain_health()
    network_name = (
        "Sepolia Testnet" if EXPECTED_CHAIN_ID == 11155111
        else ("Hardhat Local Testnet" if EXPECTED_CHAIN_ID == 31337 else f"EVM Chain {EXPECTED_CHAIN_ID}")
    )
    return {
        "status": "online" if online else "offline",
        "chain_id": EXPECTED_CHAIN_ID,
        "network": network_name,
        "contract_address": CONTRACT_ADDRESS
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
