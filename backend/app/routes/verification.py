import os
import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from ..services.hashing import calculate_hash
from ..services import blockchain
from ..services.blockchain import (
    get_independent_blockchain_record,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS
)
from ..database.mongodb import db_client
from .evidence import EVIDENCE_STORE

router = APIRouter(prefix="/verification", tags=["Integrity Verification"])

class VerificationRequest(BaseModel):
    evidence_id: Optional[str] = "EV-001"
    check_hash: Optional[str] = None
    allow_offline_fallback: Optional[bool] = False

@router.post("/verify", status_code=status.HTTP_200_OK)
async def verify_evidence_integrity(req: VerificationRequest):
    """
    Independent evidence-integrity verification:
    Does NOT treat MongoDB or local database as authoritative.
    1. Fresh File SHA-256: Calculated directly from physical evidence file bytes on disk.
    2. Database Recorded SHA-256: Read independently from stored metadata.
    3. Blockchain Ledger SHA-256: Retrieved directly from deployed smart contract state.

    Explicit Status Model:
    - VERIFIED: All three sources successfully read, IDs match, and all 3 hashes agree.
    - TAMPERED: Physical file hash differs from blockchain ledger anchor.
    - INCONSISTENT: Database hash disagrees with blockchain/file, or metadata inconsistency.
    - NOT_FOUND: Evidence absent from database and/or blockchain ledger.
    - UNAVAILABLE: Blockchain node unreachable or chain ID mismatch. Fails closed.
    """
    ev_id = req.evidence_id
    if not ev_id or not ev_id.strip():
        raise HTTPException(status_code=400, detail="Evidence ID must be provided")
    ev_id = ev_id.strip()

    # Step 0: Check required persistent storage availability
    if db_client.require_persistent_storage and not db_client.is_connected():
        return {
            "status": "success",
            "verification_status": "UNAVAILABLE",
            "evidence_id": ev_id,
            "verified": False,
            "tampered": False,
            "file_status": "unverified",
            "blockchain_status": "unverified",
            "blockchain_verified": False,
            "physical_file_hash": None,
            "database_hash": None,
            "blockchain_hash": None,
            "chain_id": EXPECTED_CHAIN_ID,
            "contract_address": CONTRACT_ADDRESS,
            "tx_hash": None,
            "file_vs_database": False,
            "database_vs_blockchain": False,
            "file_vs_blockchain": False,
            "comparisons": {
                "file_vs_database": False,
                "database_vs_blockchain": False,
                "file_vs_blockchain": False,
                "comparator_matches": False
            },
            "technical_error": "DATABASE_UNAVAILABLE",
            "explanation": "Persistent database storage is required but currently unavailable. Verification fails closed.",
            "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    # Step A & C: Read Database Metadata
    ev_record = None
    if db_client.is_connected():
        try:
            ev_record = await db_client.evidence.find_one({"evidence_id": ev_id})
        except Exception as e:
            if db_client.require_persistent_storage:
                return {
                    "status": "success",
                    "verification_status": "UNAVAILABLE",
                    "evidence_id": ev_id,
                    "verified": False,
                    "tampered": False,
                    "file_status": "unverified",
                    "blockchain_status": "unverified",
                    "blockchain_verified": False,
                    "physical_file_hash": None,
                    "database_hash": None,
                    "blockchain_hash": None,
                    "chain_id": EXPECTED_CHAIN_ID,
                    "contract_address": CONTRACT_ADDRESS,
                    "tx_hash": None,
                    "file_vs_database": False,
                    "database_vs_blockchain": False,
                    "file_vs_blockchain": False,
                    "comparisons": {
                        "file_vs_database": False,
                        "database_vs_blockchain": False,
                        "file_vs_blockchain": False,
                        "comparator_matches": False
                    },
                    "technical_error": "DATABASE_UNAVAILABLE",
                    "explanation": f"Failed to read from persistent database: {str(e)}",
                    "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }

    # If not found in DB and persistent mode is not required, check in-memory store
    if not ev_record and not db_client.require_persistent_storage:
        ev_record = EVIDENCE_STORE.get(ev_id)

    db_hash = ev_record.get("file_hash") if ev_record else None

    # Step B: Calculate Fresh File Hash from actual storage
    file_hash = None
    file_status = "missing"
    if ev_record:
        fp = ev_record.get("file_path")
        if fp and os.path.exists(fp) and os.path.isfile(fp):
            try:
                file_hash = calculate_hash(fp)
                file_status = "present"
            except Exception:
                file_status = "inaccessible"
                file_hash = None
        else:
            file_status = "missing"
            file_hash = None
    else:
        file_status = "missing"
        file_hash = None

    # Step D: Independently Read the Blockchain Contract
    chain_record, chain_err = get_independent_blockchain_record(
        ev_id,
        allow_offline_fallback=bool(req.allow_offline_fallback)
    )

    blockchain_hash = None
    blockchain_status = "unregistered"
    chain_id = EXPECTED_CHAIN_ID
    contract_addr = CONTRACT_ADDRESS
    tx_hash = None

    if chain_record:
        blockchain_status = "verified"
        blockchain_hash = chain_record.get("file_hash")
        chain_id = chain_record.get("chain_id", EXPECTED_CHAIN_ID)
        contract_addr = chain_record.get("contract_address", CONTRACT_ADDRESS)
        tx_hash = chain_record.get("tx_hash") or (ev_record.get("blockchain_tx") if ev_record else None)
    elif chain_err == "RPC_UNAVAILABLE":
        blockchain_status = "unavailable"
    elif chain_err == "CHAIN_ID_MISMATCH":
        blockchain_status = "chain_id_mismatch"
    elif chain_err == "NOT_FOUND":
        blockchain_status = "unregistered"
    else:
        blockchain_status = "error"

    # Check contract code deployment when RPC is reachable
    if blockchain_status not in ("unavailable", "chain_id_mismatch"):
        is_deployed, dep_err = blockchain.verify_contract_deployed(contract_addr)
        if dep_err == "CONTRACT_CODE_EMPTY":
            blockchain_status = "contract_not_deployed"

    # Step E: Pairwise Comparisons
    file_matches_db = bool(file_hash and db_hash and file_hash.lower() == db_hash.lower())
    database_vs_blockchain = bool(db_hash and blockchain_hash and db_hash.lower() == blockchain_hash.lower())
    file_matches_chain = bool(file_hash and blockchain_hash and file_hash.lower() == blockchain_hash.lower())

    comparator_matches = True
    if req.check_hash:
        target_check = req.check_hash.lower()
        if file_hash and file_hash.lower() != target_check:
            comparator_matches = False
        if blockchain_hash and blockchain_hash.lower() != target_check:
            comparator_matches = False
        if db_hash and db_hash.lower() != target_check:
            comparator_matches = False

    # Deterministic Precedence Rules
    technical_error = None
    explanation = ""
    verification_status = "INCONSISTENT"
    is_verified = False
    is_tampered = False

    # 1. Blockchain unavailable or network mismatch -> Fails closed
    if blockchain_status == "unavailable":
        verification_status = "UNAVAILABLE"
        is_verified = False
        is_tampered = False
        technical_error = "BLOCKCHAIN_RPC_UNAVAILABLE"
        explanation = "Blockchain RPC node is offline or unreachable. Verification fails closed; authenticity cannot be confirmed without on-chain ledger proof."

    elif blockchain_status == "chain_id_mismatch":
        verification_status = "UNAVAILABLE"
        is_verified = False
        is_tampered = False
        technical_error = "CHAIN_ID_MISMATCH"
        explanation = f"Connected blockchain network does not match expected evidence ledger chain ID ({EXPECTED_CHAIN_ID}). Verification fails closed."

    elif blockchain_status == "contract_not_deployed":
        verification_status = "INCONSISTENT"
        is_verified = False
        is_tampered = False
        technical_error = "CONTRACT_NOT_DEPLOYED"
        explanation = f"Contract address {contract_addr} contains no deployed bytecode. Local chain was reset or contract address is undeployed."

    # 2. Record not found anywhere
    elif ev_record is None and chain_record is None:
        verification_status = "NOT_FOUND"
        is_verified = False
        is_tampered = False
        technical_error = "RECORD_NOT_FOUND"
        explanation = f"Evidence identifier '{ev_id}' not found in database or blockchain registry."

    # 3. Present on blockchain but missing from local database
    elif ev_record is None:
        verification_status = "INCONSISTENT"
        is_verified = False
        is_tampered = False
        technical_error = "MISSING_FROM_DATABASE"
        explanation = f"Evidence '{ev_id}' is anchored on the blockchain, but corresponding metadata is missing from the local database."

    # 4. Blockchain reset detection: evidence marked registered in DB but missing on-chain
    elif ev_record and ev_record.get("blockchain_registered") and chain_record is None:
        verification_status = "INCONSISTENT"
        is_verified = False
        is_tampered = False
        technical_error = "BLOCKCHAIN_RESET_REGISTRATION_LOST"
        explanation = f"Evidence '{ev_id}' was registered on blockchain, but is missing from currently connected chain. Local chain reset or contract replacement detected."

    # 5. Physical evidence file is missing or unreadable
    elif file_status == "missing":
        verification_status = "TAMPERED"
        is_verified = False
        is_tampered = True
        technical_error = "PHYSICAL_FILE_MISSING"
        explanation = "Physical evidence file is missing from disk storage. Cannot verify integrity without actual file bytes."

    elif file_status == "inaccessible":
        verification_status = "ERROR"
        is_verified = False
        is_tampered = False
        technical_error = "FILE_ACCESS_ERROR"
        explanation = "I/O error reading physical evidence file from disk storage."

    # 6. Present in DB but never anchored on blockchain
    elif chain_record is None:
        verification_status = "INCONSISTENT"
        is_verified = False
        is_tampered = False
        technical_error = "NOT_REGISTERED_ON_BLOCKCHAIN"
        explanation = f"Evidence '{ev_id}' exists in local database, but has not been anchored to the blockchain. Database alone is not authoritative."

    # 7. All three sources available -> evaluate cryptographic digests
    else:
        if file_matches_chain and database_vs_blockchain and comparator_matches:
            verification_status = "VERIFIED"
            is_verified = True
            is_tampered = False
            technical_error = None
            explanation = "All three cryptographic hashes match (Physical Disk == Database == Blockchain Ledger). Evidence integrity and chain-of-custody authenticity confirmed."

            # Check block height regression if recorded
            if ev_record.get("block_number"):
                curr_height = blockchain.get_blockchain_block_number()
                if curr_height is not None and curr_height < int(ev_record.get("block_number")):
                    verification_status = "INCONSISTENT"
                    is_verified = False
                    is_tampered = False
                    technical_error = "BLOCKCHAIN_HEIGHT_REGRESSION"
                    explanation = f"Recorded block number ({ev_record.get('block_number')}) is greater than current blockchain height ({curr_height}). Local chain reset detected."

            # Check transaction receipt status if tx_hash is present
            if verification_status == "VERIFIED" and tx_hash:
                rcpt, rcpt_err = blockchain.get_transaction_receipt(tx_hash)
                if rcpt_err == "RECEIPT_NOT_FOUND":
                    verification_status = "INCONSISTENT"
                    is_verified = False
                    is_tampered = False
                    technical_error = "TRANSACTION_RECEIPT_MISSING"
                    explanation = f"Transaction receipt for '{tx_hash}' does not exist on connected blockchain. Chain reset detected."
                elif rcpt_err == "TRANSACTION_REVERTED":
                    verification_status = "INCONSISTENT"
                    is_verified = False
                    is_tampered = False
                    technical_error = "TRANSACTION_REVERTED_ON_CHAIN"
                    explanation = f"Blockchain transaction '{tx_hash}' reverted on-chain with status 0x0."

        elif file_matches_chain and not database_vs_blockchain:
            # Primary Acceptance Case: MongoDB hash manipulation!
            verification_status = "INCONSISTENT"
            is_verified = False
            is_tampered = False
            technical_error = "DATABASE_HASH_MANIPULATED"
            explanation = "Database recorded hash does not match the immutable blockchain anchor. Database record is inconsistent or has been altered, while physical file matches authentic blockchain record."

        elif not file_matches_chain:
            # Physical file differs from immutable blockchain anchor -> TAMPERED!
            verification_status = "TAMPERED"
            is_verified = False
            is_tampered = True
            technical_error = "FILE_HASH_MISMATCH_TAMPERED"
            explanation = "Physical evidence file hash differs from the immutable blockchain ledger hash. Tampering detected."

        elif not comparator_matches:
            verification_status = "TAMPERED"
            is_verified = False
            is_tampered = True
            technical_error = "COMPARATOR_MISMATCH"
            explanation = "Supplied verification hash does not match computed evidence hash."

        else:
            verification_status = "INCONSISTENT"
            is_verified = False
            is_tampered = True
            technical_error = "MULTIPLE_HASH_DISAGREEMENT"
            explanation = "Multiple hash disagreements detected across physical file, database, and blockchain records."

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return {
        "status": "success",
        "verification_status": verification_status,
        "evidence_id": ev_id,
        "verified": is_verified,
        "tampered": is_tampered,
        "file_status": file_status,
        "blockchain_status": blockchain_status,
        "blockchain_verified": bool(chain_record is not None and blockchain_status == "verified"),
        "physical_file_hash": file_hash,
        "database_hash": db_hash,
        "blockchain_hash": blockchain_hash,
        "chain_id": chain_id,
        "contract_address": contract_addr,
        "tx_hash": tx_hash,
        "file_vs_database": file_matches_db,
        "database_vs_blockchain": database_vs_blockchain,
        "file_vs_blockchain": file_matches_chain,
        "comparisons": {
            "file_vs_database": file_matches_db,
            "database_vs_blockchain": database_vs_blockchain,
            "file_vs_blockchain": file_matches_chain,
            "comparator_matches": comparator_matches
        },
        "technical_error": technical_error,
        "explanation": explanation,
        "verified_at": now
    }


@router.get("/verify", status_code=status.HTTP_200_OK)
async def verify_evidence_integrity_get(
    evidence_id: Optional[str] = "EV-001",
    check_hash: Optional[str] = None
):
    """
    GET endpoint for QR code scans and direct browser lookups.
    Delegates to the tripartite verification engine.
    """
    return await verify_evidence_integrity(VerificationRequest(
        evidence_id=evidence_id,
        check_hash=check_hash
    ))
