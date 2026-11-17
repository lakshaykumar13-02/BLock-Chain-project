import datetime
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional

from ..services.blockchain import transfer_custody_on_chain
from ..services.custody_transaction import (
    CustodyTransactionStatus,
    create_durable_transaction,
    get_durable_transaction,
    find_transaction_by_idempotency_key,
    find_active_transaction_for_evidence,
    update_transaction_state,
    reconcile_durable_transaction
)
from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..database.mongodb import db_client
from .evidence import EVIDENCE_STORE

router = APIRouter(prefix="/custody", tags=["Chain of Custody"])

import time
import logging

logger = logging.getLogger(__name__)

# In-memory audit log and concurrency stores (kept synchronized for test backward-compatibility)
AUDIT_LOGS_STORE: dict[str, list[dict]] = {}
_IN_MEMORY_TRANSFER_LOCKS: dict[str, dict] = {}
IDEMPOTENCY_STORE: dict[str, dict] = {}

class CustodyTransferRequest(BaseModel):
    evidence_id: Optional[str] = "EV-001"
    new_custodian: Optional[str] = "officer2"
    reason: Optional[str] = "Forensic analysis transfer"
    idempotency_key: Optional[str] = None


import uuid
import json
import hashlib

def calculate_transfer_payload_fingerprint(evidence_id: str, new_custodian: str, reason: str) -> str:
    """Compute deterministic SHA-256 fingerprint of transfer payload for idempotency verification."""
    data = {
        "evidence_id": str(evidence_id).strip(),
        "new_custodian": str(new_custodian).strip(),
        "reason": str(reason).strip()
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def acquire_custody_transfer_lock(
    evidence_id: str,
    actor: str,
    idempotency_key: Optional[str] = None,
    lease_seconds: float = 30.0,
    wait_timeout: float = 0.4
) -> tuple[bool, Optional[str], Optional[str], int]:
    """
    Acquire atomic, lease-based transfer lock on evidence to ensure multi-worker mutual exclusion.
    Generates a unique lock_token and reads expected custody_version as a fencing token.
    Returns (acquired: bool, lock_token: Optional[str], reason: Optional[str], expected_version: int).
    """
    import asyncio
    start_time = time.time()
    lease_duration = lease_seconds

    while True:
        now = time.time()
        lock_token = uuid.uuid4().hex

        # 0. In-memory simulated lock check (ensures active locks in test harness or memory are respected)
        if evidence_id in _IN_MEMORY_TRANSFER_LOCKS:
            lock_info = _IN_MEMORY_TRANSFER_LOCKS[evidence_id]
            if lock_info.get("status") == "LOCKED" and lock_info.get("expires_at", 0) > now:
                if time.time() - start_time >= wait_timeout:
                    return False, None, "LOCKED", 0
                await asyncio.sleep(0.02)
                continue

        # 1. MongoDB atomic conditional acquisition when connected and evidence exists in MongoDB
        ev_doc = None
        if db_client.is_connected():
            try:
                ev_doc = await db_client.evidence.find_one({"evidence_id": evidence_id})
                if not ev_doc and evidence_id not in EVIDENCE_STORE:
                    return False, None, "NOT_FOUND", 0

                if ev_doc:
                    expected_version = ev_doc.get("custody_version", 0)
                    res = await db_client.evidence.update_one(
                        {
                            "evidence_id": evidence_id,
                            "$or": [
                                {"transfer_lock": {"$exists": False}},
                                {"transfer_lock.status": {"$ne": "LOCKED"}},
                                {"transfer_lock.expires_at": {"$lt": now}}
                            ]
                        },
                        {
                            "$set": {
                                "transfer_lock": {
                                    "status": "LOCKED",
                                    "actor": actor,
                                    "lock_token": lock_token,
                                    "idempotency_key": idempotency_key,
                                    "locked_at": now,
                                    "expires_at": now + lease_duration,
                                    "fencing_version": expected_version
                                }
                            }
                        }
                    )
                    if res.modified_count > 0:
                        return True, lock_token, None, expected_version
            except Exception as e:
                logger.debug(f"MongoDB acquire_custody_transfer_lock exception: {e}")
                if db_client.require_persistent_storage:
                    raise

        # 2. In-memory lock (for isolated test environments or in-memory evidence records)
        if not db_client.is_connected() or not ev_doc:
            ev_rec = EVIDENCE_STORE.get(evidence_id, {})
            expected_version = ev_rec.get("custody_version", 0)
            if evidence_id not in _IN_MEMORY_TRANSFER_LOCKS or _IN_MEMORY_TRANSFER_LOCKS[evidence_id].get("status") != "LOCKED" or _IN_MEMORY_TRANSFER_LOCKS[evidence_id].get("expires_at", 0) <= now:
                _IN_MEMORY_TRANSFER_LOCKS[evidence_id] = {
                    "status": "LOCKED",
                    "actor": actor,
                    "lock_token": lock_token,
                    "idempotency_key": idempotency_key,
                    "locked_at": now,
                    "expires_at": now + lease_duration,
                    "fencing_version": expected_version
                }
                return True, lock_token, None, expected_version

        if time.time() - start_time >= wait_timeout:
            return False, None, "LOCKED", 0

        await asyncio.sleep(0.02)


async def renew_custody_transfer_lock(
    evidence_id: str,
    lock_token: str,
    additional_seconds: float = 30.0
) -> bool:
    """
    Safely extend lease for long-running operations.
    Fails closed if the lock was already lost to a newer worker.
    """
    now = time.time()
    if db_client.is_connected():
        try:
            ev_doc = await db_client.evidence.find_one({"evidence_id": evidence_id})
            if ev_doc:
                res = await db_client.evidence.update_one(
                    {
                        "evidence_id": evidence_id,
                        "transfer_lock.lock_token": lock_token,
                        "transfer_lock.status": "LOCKED"
                    },
                    {
                        "$set": {
                            "transfer_lock.expires_at": now + additional_seconds
                        }
                    }
                )
                return res.modified_count > 0
        except Exception as e:
            logger.debug(f"renew_custody_transfer_lock db exception: {e}")
            return False

    if evidence_id in _IN_MEMORY_TRANSFER_LOCKS:
        lock_info = _IN_MEMORY_TRANSFER_LOCKS[evidence_id]
        if lock_info.get("lock_token") == lock_token and lock_info.get("status") == "LOCKED":
            lock_info["expires_at"] = now + additional_seconds
            return True
    return False


async def release_custody_transfer_lock(
    evidence_id: str,
    lock_token: Optional[str] = None,
    new_custodian: Optional[str] = None,
    expected_version: Optional[int] = None,
    failed: bool = False,
    err_msg: Optional[str] = None
) -> bool:
    """
    Release atomic custody transfer lock using owner lock_token and fencing version.
    Guarantees that a stale worker whose lease expired cannot commit or overwrite another worker's lock.
    Returns True if successfully released, False if lock ownership was lost.
    """
    now = time.time()
    success = True
    in_db = False
    if db_client.is_connected():
        try:
            ev_doc = await db_client.evidence.find_one({"evidence_id": evidence_id})
            if ev_doc:
                in_db = True
                update_fields: dict = {
                    "transfer_lock.status": "FAILED" if failed else "UNLOCKED",
                    "transfer_lock.released_at": now
                }
                if err_msg:
                    update_fields["transfer_lock.error"] = err_msg
                if not failed and new_custodian:
                    update_fields["custodian"] = new_custodian

                update_doc: dict = {"$set": update_fields}
                if not failed:
                    update_doc["$inc"] = {"custody_version": 1}

                filter_query: dict = {"evidence_id": evidence_id}
                if lock_token:
                    filter_query["transfer_lock.lock_token"] = lock_token
                if not failed and expected_version is not None:
                    if expected_version == 0:
                        filter_query["$or"] = [
                            {"custody_version": 0},
                            {"custody_version": {"$exists": False}}
                        ]
                    else:
                        filter_query["custody_version"] = expected_version

                res = await db_client.evidence.update_one(filter_query, update_doc)
                if res.modified_count == 0:
                    logger.warning(
                        f"Fencing violation or lost lease during release on evidence '{evidence_id}'. "
                        f"Lock token '{lock_token}' no longer matches active lease."
                    )
                    success = False
        except Exception as e:
            logger.debug(f"release_custody_transfer_lock db exception: {e}")
            success = False

    if not in_db:
        if evidence_id not in _IN_MEMORY_TRANSFER_LOCKS:
            # Lock does not exist or already expired/released
            if lock_token:
                return False
        else:
            lock_info = _IN_MEMORY_TRANSFER_LOCKS[evidence_id]
            if lock_token and lock_info.get("lock_token") != lock_token:
                return False
            # Fencing check: verify custody_version has not advanced past expected_version
            if not failed and expected_version is not None:
                current_ver = EVIDENCE_STORE.get(evidence_id, {}).get("custody_version", 0)
                if current_ver != expected_version:
                    return False
            if failed:
                _IN_MEMORY_TRANSFER_LOCKS[evidence_id]["status"] = "FAILED"
            else:
                _IN_MEMORY_TRANSFER_LOCKS.pop(evidence_id, None)
                if evidence_id in EVIDENCE_STORE:
                    EVIDENCE_STORE[evidence_id]["custody_version"] = EVIDENCE_STORE[evidence_id].get("custody_version", 0) + 1
                    if new_custodian:
                        EVIDENCE_STORE[evidence_id]["custodian"] = new_custodian
            return True

    return success


@router.post("/transfer", status_code=status.HTTP_200_OK)
async def transfer_custody(
    req: CustodyTransferRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """
    Execute chain-of-custody transfer with multi-worker concurrency protection and idempotency.
    Allowed roles: ADMIN, INVESTIGATOR.
    Updates active custodian, logs to immutable tamper-evident audit trail, and records on-chain.
    """
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent database storage is required but currently unavailable"
        )

    from ..services.audit_trail import record_custody_event

    ev_id = req.evidence_id or "EV-001"
    new_custodian = req.new_custodian or "officer2"
    reason = req.reason or "Custody handover"
    idem_key = (req.idempotency_key or "").strip() or None
    actor = current_user.get("username", "investigator1")

    payload_fp = calculate_transfer_payload_fingerprint(ev_id, new_custodian, reason)

    # 1. Authoritative Durable Transaction & Idempotency Check with Safe Reconciliation
    if idem_key:
        cached_record = None
        if db_client.is_connected():
            try:
                cached_record = await db_client.db["idempotency_records"].find_one({"idempotency_key": idem_key}, {"_id": 0})
            except Exception:
                pass
        if not cached_record and idem_key in IDEMPOTENCY_STORE:
            cached_record = IDEMPOTENCY_STORE[idem_key]

        if cached_record:
            # Check Actor Scoping
            rec_actor = cached_record.get("actor_id")
            if rec_actor and rec_actor != actor:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Idempotency key '{idem_key}' was previously used by a different actor ('{rec_actor}')."
                )

            # Check Payload Fingerprint
            rec_fp = cached_record.get("payload_fingerprint")
            if rec_fp and rec_fp != payload_fp:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Idempotency key '{idem_key}' was previously used with a different request payload."
                )

            # Check IN_PROGRESS state (concurrent in-flight request)
            rec_status = cached_record.get("status")
            if rec_status == "IN_PROGRESS":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Operation with idempotency key '{idem_key}' is currently in progress. Please retry after completion."
                )

            if rec_status == "COMPLETED" and "response" in cached_record:
                logger.info(f"Returning authoritative cached response for key '{idem_key}'")
                return cached_record["response"]

        existing_tx = await find_transaction_by_idempotency_key(idem_key)
        if existing_tx:
            # Check Actor Scoping
            rec_actor = existing_tx.get("actor_id")
            if rec_actor and rec_actor != actor:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Idempotency key '{idem_key}' was previously used by a different actor ('{rec_actor}')."
                )

            # Check Payload Fingerprint
            rec_fp = existing_tx.get("payload_fingerprint")
            if rec_fp and rec_fp != payload_fp:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Idempotency key '{idem_key}' was previously used with a different request payload."
                )

            # Fast-path for already completed transactions
            if existing_tx.get("status") == CustodyTransactionStatus.COMPLETED.value and existing_tx.get("response"):
                logger.info(f"Returning authoritative cached response for key '{idem_key}'")
                return existing_tx["response"]

            # Check if existing transaction is actively in-progress (lease currently held and not expired)
            ex_status = existing_tx.get("status")
            if ex_status in (
                CustodyTransactionStatus.PREPARED.value,
                CustodyTransactionStatus.SUBMITTED.value,
                CustodyTransactionStatus.CONFIRMED.value,
                CustodyTransactionStatus.ANCHOR_SUBMITTED.value
            ):
                now = time.time()
                is_active = False
                if ev_id in _IN_MEMORY_TRANSFER_LOCKS:
                    l = _IN_MEMORY_TRANSFER_LOCKS[ev_id]
                    if l.get("status") == "LOCKED" and l.get("expires_at", 0) > now:
                        is_active = True
                if not is_active and db_client.is_connected():
                    try:
                        ev_doc = await db_client.evidence.find_one({"evidence_id": ev_id})
                        if ev_doc and ev_doc.get("transfer_lock", {}).get("status") == "LOCKED":
                            if ev_doc.get("transfer_lock", {}).get("expires_at", 0) > now:
                                is_active = True
                    except Exception:
                        pass
                if is_active:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Operation with idempotency key '{idem_key}' is currently in progress by active worker. Please retry once complete."
                    )

            # Safe retry & recovery logic: attempt reconciliation on existing in-flight / interrupted transaction
            reconciled, rec_tx, rec_err = await reconcile_durable_transaction(
                existing_tx["transaction_id"],
                allow_offline_fallback=True
            )
            if reconciled:
                if rec_tx.get("response"):
                    return rec_tx["response"]
                resp = {
                    "status": "success",
                    "message": f"Custody of evidence {ev_id} transferred to {new_custodian} (Reconciled)",
                    "record": {"evidence_id": ev_id, "custodian": new_custodian, "reconciled": True},
                    "blockchain": {"tx_hash": rec_tx.get("transfer_tx_hash"), "status": "confirmed", "reconciled": True},
                    "transaction_id": rec_tx["transaction_id"]
                }
                await update_transaction_state(rec_tx["transaction_id"], CustodyTransactionStatus.COMPLETED, {"response": resp})
                return resp
            else:
                if rec_err == "BLOCKCHAIN_RPC_UNAVAILABLE":
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Transaction with idempotency key '{idem_key}' is pending but blockchain RPC is unreachable for reconciliation."
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Operation with idempotency key '{idem_key}' is in state '{rec_tx.get('status')}'. Reconciliation: {rec_err}."
                )

    # Check for active unresolved reconciliation blockers on this evidence item
    active_unresolved = await find_active_transaction_for_evidence(ev_id)
    if active_unresolved and active_unresolved.get("status") == CustodyTransactionStatus.RECONCILIATION_REQUIRED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Custody transfer blocked: evidence '{ev_id}' has pending transaction '{active_unresolved.get('transaction_id')}' requiring reconciliation."
        )

    prev_custodian = actor
    case_id = "CV-2026-001"

    # 2. Concurrency Lock: Atomic acquisition across workers with fencing token
    acquired, lock_token, lock_err, expected_version = await acquire_custody_transfer_lock(ev_id, actor, idem_key)
    if not acquired:
        if lock_err == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=f"Evidence record '{ev_id}' not found")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Concurrent custody transfer in progress for evidence '{ev_id}'. Please retry once the active operation completes."
        )

    # 3. Durable Transaction Intent: Persist BEFORE any external RPC broadcast
    durable_tx = await create_durable_transaction(
        evidence_id=ev_id,
        actor_id=actor,
        new_custodian=new_custodian,
        reason=reason,
        idempotency_key=idem_key,
        payload_fingerprint=payload_fp,
        lock_token=lock_token,
        fencing_version=expected_version
    )
    tx_id = durable_tx["transaction_id"]

    if idem_key:
        in_progress_doc = {
            "idempotency_key": idem_key,
            "actor_id": actor,
            "evidence_id": ev_id,
            "payload_fingerprint": payload_fp,
            "status": "IN_PROGRESS",
            "transaction_id": tx_id,
            "started_at": time.time()
        }
        IDEMPOTENCY_STORE[idem_key] = in_progress_doc
        if db_client.is_connected():
            try:
                await db_client.db["idempotency_records"].update_one(
                    {"idempotency_key": idem_key},
                    {"$set": in_progress_doc},
                    upsert=True
                )
            except Exception:
                pass

    try:
        # Read current state from DB or memory
        if db_client.is_connected():
            try:
                ev_doc = await db_client.evidence.find_one({"evidence_id": ev_id})
                if ev_doc:
                    prev_custodian = ev_doc.get("custodian", prev_custodian)
                    case_id = ev_doc.get("case_id", case_id)
            except Exception:
                pass

        if ev_id in EVIDENCE_STORE:
            prev_custodian = EVIDENCE_STORE[ev_id].get("custodian", prev_custodian)
            case_id = EVIDENCE_STORE[ev_id].get("case_id", case_id)

        # 4. On-chain transfer broadcast & immediate state transition to SUBMITTED
        chain_receipt = transfer_custody_on_chain(ev_id, new_custodian, reason)
        transfer_tx_hash = chain_receipt.get("tx_hash")
        await update_transaction_state(
            tx_id,
            CustodyTransactionStatus.SUBMITTED,
            {"transfer_tx_hash": transfer_tx_hash}
        )

        # 5. Confirm transfer transaction receipt & transition to CONFIRMED
        await update_transaction_state(
            tx_id,
            CustodyTransactionStatus.CONFIRMED,
            {"transfer_block_number": chain_receipt.get("block_number")}
        )

        # 6. Concurrency-controlled, canonically hashed, tamper-evident custody event & on-chain anchor
        log_entry = await record_custody_event(
            evidence_id=ev_id,
            action="CUSTODY_TRANSFER",
            actor_id=actor,
            case_id=case_id,
            details={
                "previous_custodian": prev_custodian,
                "new_custodian": new_custodian,
                "reason": reason
            },
            anchor_reference=transfer_tx_hash
        )

        # Transition to ANCHOR_SUBMITTED
        anchor_tx_hash = log_entry.get("anchor_reference")
        await update_transaction_state(
            tx_id,
            CustodyTransactionStatus.ANCHOR_SUBMITTED,
            {
                "anchor_tx_hash": anchor_tx_hash,
                "anchor_sequence_number": log_entry.get("sequence_number"),
                "event_hash": log_entry.get("event_hash"),
                "previous_event_hash": log_entry.get("previous_event_hash")
            }
        )

        # Update in-memory store
        if ev_id in EVIDENCE_STORE:
            EVIDENCE_STORE[ev_id]["custodian"] = new_custodian

        # 7. Release lock and update custodian in persistent database with fencing verification
        committed = await release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=lock_token,
            new_custodian=new_custodian,
            expected_version=expected_version,
            failed=False
        )
        if not committed:
            await update_transaction_state(
                tx_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": "Fencing violation: lock lease expired or was preempted by another worker before commit."}
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Fencing violation: lock lease expired or was preempted by another worker before commit. Transaction marked RECONCILIATION_REQUIRED."
            )

        response_data = {
            "status": "success",
            "message": f"Custody of evidence {ev_id} transferred to {new_custodian}",
            "record": log_entry,
            "blockchain": chain_receipt,
            "transaction_id": tx_id
        }

        # 8. Mark transaction and idempotency store as COMPLETED
        await update_transaction_state(
            tx_id,
            CustodyTransactionStatus.COMPLETED,
            {"response": response_data}
        )

        if idem_key:
            completed_doc = {
                "idempotency_key": idem_key,
                "actor_id": actor,
                "evidence_id": ev_id,
                "payload_fingerprint": payload_fp,
                "status": "COMPLETED",
                "response": response_data,
                "completed_at": time.time()
            }
            IDEMPOTENCY_STORE[idem_key] = completed_doc
            if db_client.is_connected():
                try:
                    await db_client.db["idempotency_records"].update_one(
                        {"idempotency_key": idem_key},
                        {"$set": completed_doc},
                        upsert=True
                    )
                except Exception:
                    pass

        return response_data

    except Exception as e:
        curr_tx = await get_durable_transaction(tx_id)
        if curr_tx and curr_tx.get("status") in (
            CustodyTransactionStatus.SUBMITTED.value,
            CustodyTransactionStatus.CONFIRMED.value,
            CustodyTransactionStatus.ANCHOR_SUBMITTED.value
        ):
            await update_transaction_state(
                tx_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": str(e)}
            )
        elif curr_tx and curr_tx.get("status") == CustodyTransactionStatus.PREPARED.value:
            await update_transaction_state(
                tx_id,
                CustodyTransactionStatus.FAILED,
                {"error_message": str(e)}
            )

        await release_custody_transfer_lock(ev_id, lock_token=lock_token, failed=True, err_msg=str(e))
        if idem_key:
            if db_client.is_connected():
                try:
                    await db_client.db["idempotency_records"].update_one(
                        {"idempotency_key": idem_key, "status": "IN_PROGRESS"},
                        {"$set": {"status": "FAILED", "error": str(e)}}
                    )
                except Exception:
                    pass
            if idem_key in IDEMPOTENCY_STORE and IDEMPOTENCY_STORE[idem_key].get("status") == "IN_PROGRESS":
                IDEMPOTENCY_STORE.pop(idem_key, None)
        if isinstance(e, HTTPException):
            raise
        if db_client.require_persistent_storage:
            raise HTTPException(status_code=500, detail=f"Failed to execute custody transfer: {e}")
        raise

@router.get("/history/{evidence_id}")
async def get_custody_history(
    evidence_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve complete custody log history for an evidence item. Allowed roles: All authenticated."""
    from ..services.audit_trail import get_stored_custody_events, record_custody_event
    events = await get_stored_custody_events(evidence_id)
    if not events and evidence_id in EVIDENCE_STORE:
        ev = EVIDENCE_STORE[evidence_id]
        genesis = await record_custody_event(
            evidence_id=evidence_id,
            action="EVIDENCE_INGESTION",
            actor_id=ev.get("custodian", "investigator1"),
            case_id=ev.get("case_id", "CV-2026-001"),
            details={
                "file_hash": ev.get("file_hash", ""),
                "filename": ev.get("filename", "evidence.bin"),
                "previous_custodian": "None",
                "new_custodian": ev.get("custodian", "investigator1"),
                "reason": "Initial digital evidence ingestion"
            },
            custom_timestamp=ev.get("uploaded_at")
        )
        events = [genesis]
    return events


@router.get("/transactions/{evidence_id}")
async def list_custody_transactions(
    evidence_id: str,
    current_user: dict = Depends(get_current_user)
):
    """List all durable custody transactions for an evidence item."""
    from ..services.custody_transaction import CUSTODY_TRANSACTIONS_STORE
    txs = []
    if db_client.is_connected():
        try:
            cursor = db_client.db["custody_transactions"].find({"evidence_id": evidence_id}, {"_id": 0}).sort("created_at", -1)
            async for doc in cursor:
                txs.append(doc)
        except Exception:
            pass
    if not txs:
        txs = [dict(t) for t in CUSTODY_TRANSACTIONS_STORE.values() if t.get("evidence_id") == evidence_id]
    return txs


@router.get("/transaction/{transaction_id}")
async def get_transaction_details(
    transaction_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve details of a durable custody transaction."""
    tx = await get_durable_transaction(transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction '{transaction_id}' not found.")
    return tx


@router.post("/transaction/reconcile/{transaction_id}")
@router.post("/transactions/reconcile/{transaction_id}")
@router.post("/reconcile/{transaction_id}")
async def reconcile_transaction_endpoint(
    transaction_id: str,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """Execute on-demand reconciliation of an in-flight or interrupted transaction."""
    reconciled, tx, err_code = await reconcile_durable_transaction(transaction_id, allow_offline_fallback=False)
    if not reconciled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reconciliation failed with error: {err_code}. Transaction status: {tx.get('status')}."
        )
    return {"status": "success", "message": "Transaction reconciled successfully", "transaction": tx}
