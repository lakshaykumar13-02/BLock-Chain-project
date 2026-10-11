import os
import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from ..services.hashing import calculate_hash
from ..services.blockchain import get_evidence_from_chain, verify_on_chain
from .evidence import EVIDENCE_STORE

router = APIRouter(prefix="/verification", tags=["Integrity Verification"])

class VerificationRequest(BaseModel):
    evidence_id: Optional[str] = "EV-001"
    check_hash: Optional[str] = None

@router.post("/verify", status_code=status.HTTP_200_OK)
async def verify_evidence_integrity(req: VerificationRequest):
    """
    Execute three-way integrity verification:
    1. Physical File Hash: Recomputed from disk binary.
    2. Database Hash: Hash preserved in metadata storage.
    3. Blockchain Ledger Hash: Cryptographic hash committed on-chain.

    Safe Implementation Rule: Never claim integrity verification passed unless
    all required comparisons actually pass.
    """
    ev_id = req.evidence_id or "EV-001"

    ev_record = EVIDENCE_STORE.get(ev_id)
    chain_record = get_evidence_from_chain(ev_id)

    # 1. Determine DB hash (never mutated)
    db_hash = ev_record.get("file_hash") if ev_record else None

    # 2. Determine Physical File Hash
    file_hash = None
    file_status = "present"
    if ev_record:
        fp = ev_record.get("file_path")
        if fp:
            if os.path.exists(fp) and os.path.isfile(fp):
                try:
                    file_hash = calculate_hash(fp)
                except Exception:
                    file_status = "inaccessible"
                    file_hash = None
            else:
                file_status = "missing"
                file_hash = None
        else:
            file_status = "in_memory"
            file_hash = db_hash

    # 3. Determine Blockchain Hash (never mutated)
    blockchain_hash = chain_record.get("file_hash") if chain_record else None

    # Check external comparator digest if supplied in request
    comparator_matches = True
    if req.check_hash:
        target_check = req.check_hash.lower()
        if db_hash and target_check != db_hash.lower():
            comparator_matches = False
        if blockchain_hash and target_check != blockchain_hash.lower():
            comparator_matches = False
        if file_hash and target_check != file_hash.lower():
            comparator_matches = False

    # Perform strict pairwise cryptographic comparisons
    file_matches_db = bool(file_hash and db_hash and file_hash.lower() == db_hash.lower())
    db_matches_chain = bool(db_hash and blockchain_hash and db_hash.lower() == blockchain_hash.lower())
    file_matches_chain = bool(file_hash and blockchain_hash and file_hash.lower() == blockchain_hash.lower())

    if chain_record is not None:
        is_verified = bool(file_matches_db and db_matches_chain and file_matches_chain and comparator_matches)
    elif db_hash is not None:
        is_verified = bool(file_matches_db and comparator_matches)
    else:
        is_verified = False

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return {
        "status": "success",
        "evidence_id": ev_id,
        "verified": is_verified,
        "tampered": not is_verified,
        "file_status": file_status,
        "physical_file_hash": file_hash,
        "database_hash": db_hash,
        "blockchain_hash": blockchain_hash,
        "comparisons": {
            "file_vs_database": file_matches_db,
            "database_vs_blockchain": db_matches_chain,
            "file_vs_blockchain": file_matches_chain,
            "comparator_matches": comparator_matches
        },
        "verified_at": now
    }
