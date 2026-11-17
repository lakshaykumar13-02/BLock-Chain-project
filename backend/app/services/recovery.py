import os
import datetime
import logging
from pathlib import Path
from typing import Optional

from ..database.mongodb import db_client
from ..services.storage import STORAGE_DIR, get_storage_path
from ..services.blockchain import (
    check_blockchain_health,
    get_blockchain_chain_id,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS,
    verify_contract_deployed,
    get_blockchain_block_number,
    get_transaction_receipt,
    query_contract_evidence
)
from ..routes.evidence import EVIDENCE_STORE

logger = logging.getLogger(__name__)

async def get_system_diagnostics() -> dict:
    """
    Produce non-sensitive system health and recovery diagnostics.
    Safe for monitoring: leaks zero passwords, private keys, or infrastructure secrets.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 1. MongoDB Status
    mongo_connected = db_client.is_connected()
    mongo_responsive = await db_client.ping() if mongo_connected else False
    persistence_mode = db_client.get_persistence_mode()

    # 2. Blockchain RPC & Contract Status
    chain_connected = check_blockchain_health()
    observed_chain_id = get_blockchain_chain_id() if chain_connected else None
    chain_id_valid = observed_chain_id == EXPECTED_CHAIN_ID

    contract_deployed = False
    contract_status = "unverified"
    if chain_connected and chain_id_valid:
        is_dep, dep_err = verify_contract_deployed(CONTRACT_ADDRESS)
        contract_deployed = is_dep
        contract_status = "deployed" if is_dep else (dep_err or "undeployed")
    elif not chain_connected:
        contract_status = "rpc_unavailable"
    else:
        contract_status = "chain_id_mismatch"

    # 3. Storage Directory Status
    storage_path = get_storage_path()
    storage_accessible = storage_path.exists() and storage_path.is_dir()

    # Count files and potential discrepancies safely
    total_physical_files = 0
    if storage_accessible:
        try:
            total_physical_files = len([
                f for f in os.listdir(storage_path)
                if os.path.isfile(os.path.join(storage_path, f)) and not f.startswith(".")
            ])
        except Exception:
            pass

    # Read evidence record count from DB or memory
    evidence_count = 0
    if mongo_connected:
        try:
            evidence_count = await db_client.evidence.count_documents({})
        except Exception:
            evidence_count = len(EVIDENCE_STORE)
    else:
        evidence_count = len(EVIDENCE_STORE)

    ready_for_verification = (
        (mongo_connected or not db_client.require_persistent_storage)
        and chain_connected
        and chain_id_valid
        and contract_deployed
        and storage_accessible
    )

    issues = []
    if db_client.require_persistent_storage and not mongo_connected:
        issues.append("Persistent MongoDB database is offline in required-persistence mode.")
    if not chain_connected:
        issues.append("Blockchain RPC node is offline or unreachable.")
    elif not chain_id_valid:
        issues.append(f"Blockchain Chain ID mismatch: expected {EXPECTED_CHAIN_ID}, observed {observed_chain_id}.")
    elif not contract_deployed:
        issues.append(f"Contract bytecode absent at configured address {CONTRACT_ADDRESS}.")
    if not storage_accessible:
        issues.append(f"Evidence physical storage directory is inaccessible.")

    return {
        "status": "healthy" if (ready_for_verification and not issues) else "degraded",
        "ready_for_verification": ready_for_verification,
        "database": {
            "status": "connected" if mongo_responsive else ("connected_unresponsive" if mongo_connected else "disconnected"),
            "persistence_mode": persistence_mode,
            "require_persistent_storage": db_client.require_persistent_storage,
            "records_count": evidence_count
        },
        "blockchain": {
            "rpc_reachable": chain_connected,
            "expected_chain_id": EXPECTED_CHAIN_ID,
            "observed_chain_id": observed_chain_id,
            "chain_id_matched": chain_id_valid,
            "contract_address": CONTRACT_ADDRESS,
            "contract_status": contract_status,
            "contract_code_deployed": contract_deployed
        },
        "storage": {
            "accessible": storage_accessible,
            "total_physical_files": total_physical_files
        },
        "issues": issues,
        "diagnostics_timestamp": now
    }

async def run_system_consistency_check() -> dict:
    """
    Authoritative consistency check between physical files, database records, and blockchain.
    Detects orphaned files, missing evidence files, and lost blockchain registrations.
    Does NOT automatically delete evidence or alter authoritative records.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    missing_files = []
    orphaned_files = []
    blockchain_inconsistencies = []

    # 1. Fetch all database records
    records = []
    if db_client.is_connected():
        try:
            cursor = db_client.evidence.find({}, {"_id": 0})
            records = await cursor.to_list(length=10000)
        except Exception as e:
            logger.error(f"Failed to query database for consistency check: {e}")
    if not records:
        records = list(EVIDENCE_STORE.values())

    known_file_paths = set()
    known_stored_names = set()

    for rec in records:
        ev_id = rec.get("evidence_id")
        fp = rec.get("file_path")
        stored_name = rec.get("stored_filename") or rec.get("filename")

        if fp:
            known_file_paths.add(os.path.abspath(fp).lower())
            if not os.path.exists(fp) or not os.path.isfile(fp):
                missing_files.append({
                    "evidence_id": ev_id,
                    "expected_file_path": fp,
                    "issue": "PHYSICAL_FILE_MISSING"
                })
        else:
            missing_files.append({
                "evidence_id": ev_id,
                "expected_file_path": None,
                "issue": "NO_FILE_PATH_RECORDED"
            })

        if stored_name:
            known_stored_names.add(stored_name.lower())

        # Check blockchain consistency if marked registered
        if rec.get("blockchain_registered"):
            chain_rec, q_err = query_contract_evidence(ev_id)
            if q_err == "NOT_FOUND":
                blockchain_inconsistencies.append({
                    "evidence_id": ev_id,
                    "issue": "REGISTRATION_LOST_AFTER_RESET",
                    "detail": "Marked registered in DB, but missing from connected contract state."
                })
            elif chain_rec:
                if chain_rec.get("file_hash", "").lower() != rec.get("file_hash", "").lower():
                    blockchain_inconsistencies.append({
                        "evidence_id": ev_id,
                        "issue": "HASH_MISMATCH_ON_CHAIN",
                        "database_hash": rec.get("file_hash"),
                        "blockchain_hash": chain_rec.get("file_hash")
                    })

    # 2. Check for orphaned files on disk
    storage_path = get_storage_path()
    if storage_path.exists() and storage_path.is_dir():
        try:
            for entry in os.listdir(storage_path):
                full_path = os.path.join(storage_path, entry)
                if os.path.isfile(full_path) and not entry.startswith("."):
                    if os.path.abspath(full_path).lower() not in known_file_paths and entry.lower() not in known_stored_names:
                        orphaned_files.append({
                            "filename": entry,
                            "path": full_path,
                            "size_bytes": os.path.getsize(full_path),
                            "issue": "ORPHANED_FILE_NO_DB_RECORD"
                        })
        except Exception as e:
            logger.error(f"Error scanning storage directory: {e}")

    recommendations = []
    if missing_files:
        recommendations.append(
            f"Found {len(missing_files)} evidence records with missing physical files on disk. "
            "Inspect forensic backups or restore physical evidence files."
        )
    if orphaned_files:
        recommendations.append(
            f"Found {len(orphaned_files)} orphaned files on disk without matching database records. "
            "Archive or ingest through authorized chain-of-custody intake. Do NOT delete automatically."
        )
    if blockchain_inconsistencies:
        recommendations.append(
            f"Found {len(blockchain_inconsistencies)} blockchain state discrepancies. "
            "If local chain was reset, perform authorized re-anchoring from trusted audit checkpoints."
        )

    is_consistent = not missing_files and not orphaned_files and not blockchain_inconsistencies

    return {
        "timestamp": now,
        "is_consistent": is_consistent,
        "total_records_checked": len(records),
        "missing_physical_files": missing_files,
        "orphaned_physical_files": orphaned_files,
        "blockchain_inconsistencies": blockchain_inconsistencies,
        "recommendations": recommendations
    }
