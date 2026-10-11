import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from ..services.blockchain import transfer_custody_on_chain
from .evidence import EVIDENCE_STORE

router = APIRouter(prefix="/custody", tags=["Chain of Custody"])

# In-memory audit log store
AUDIT_LOGS_STORE: dict[str, list[dict]] = {}

class CustodyTransferRequest(BaseModel):
    evidence_id: Optional[str] = "EV-001"
    new_custodian: Optional[str] = "officer2"
    reason: Optional[str] = "Forensic analysis transfer"

@router.post("/transfer", status_code=status.HTTP_200_OK)
async def transfer_custody(req: CustodyTransferRequest):
    """
    Execute chain-of-custody transfer.
    Updates active custodian, logs to immutable audit trail, and records on-chain.
    """
    ev_id = req.evidence_id or "EV-001"
    new_custodian = req.new_custodian or "officer2"
    reason = req.reason or "Custody handover"

    prev_custodian = "investigator1"
    if ev_id in EVIDENCE_STORE:
        prev_custodian = EVIDENCE_STORE[ev_id].get("custodian", "investigator1")
        EVIDENCE_STORE[ev_id]["custodian"] = new_custodian

    # On-chain transfer
    chain_receipt = transfer_custody_on_chain(ev_id, new_custodian, reason)

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_entry = {
        "log_id": f"AUD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "evidence_id": ev_id,
        "action": "CUSTODY_TRANSFER",
        "previous_custodian": prev_custodian,
        "new_custodian": new_custodian,
        "reason": reason,
        "timestamp": now,
        "blockchain_tx": chain_receipt["tx_hash"]
    }

    if ev_id not in AUDIT_LOGS_STORE:
        AUDIT_LOGS_STORE[ev_id] = []
    AUDIT_LOGS_STORE[ev_id].append(log_entry)

    return {
        "status": "success",
        "message": f"Custody of evidence {ev_id} transferred to {new_custodian}",
        "record": log_entry,
        "blockchain": chain_receipt
    }

@router.get("/history/{evidence_id}")
async def get_custody_history(evidence_id: str):
    """Retrieve complete custody log history for an evidence item."""
    return AUDIT_LOGS_STORE.get(evidence_id, [])
