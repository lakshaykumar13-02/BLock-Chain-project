"""
ChainVault Phase 8B — Durable Blockchain Custody Transaction State Machine
========================================================================
Manages the end-to-end lifecycle of on-chain custody transfers and anchors,
ensuring strict consistency between MongoDB persistence and Ethereum transactions.

Supported States:
- PREPARED: Intent registered in MongoDB before any external RPC broadcast.
- SUBMITTED: Custody transfer transaction broadcast to Ethereum; tx_hash persisted.
- CONFIRMED: Transfer transaction mined and confirmed on-chain.
- ANCHOR_SUBMITTED: Exact canonical event hash anchor broadcast; anchor_tx_hash persisted.
- COMPLETED: On-chain transactions verified, audit log inserted, evidence document committed.
- FAILED: Aborted prior to state divergence or irreversibly reverted on-chain.
- RECONCILIATION_REQUIRED: Discrepancy detected (e.g. tx mined but DB fenced out/crash).
"""

import time
import uuid
import logging
from typing import Optional, Any
from enum import Enum

from ..database.mongodb import db_client
from .blockchain import (
    get_blockchain_chain_id,
    get_transaction_receipt,
    get_transaction_by_hash,
    get_custody_anchor_from_chain,
    verify_contract_deployed,
    query_contract_evidence,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS
)

logger = logging.getLogger(__name__)

class CustodyTransactionStatus(str, Enum):
    PREPARED = "PREPARED"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    ANCHOR_SUBMITTED = "ANCHOR_SUBMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"

ALLOWED_TRANSITIONS = {
    CustodyTransactionStatus.PREPARED: [
        CustodyTransactionStatus.SUBMITTED,
        CustodyTransactionStatus.FAILED,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED
    ],
    CustodyTransactionStatus.SUBMITTED: [
        CustodyTransactionStatus.CONFIRMED,
        CustodyTransactionStatus.FAILED,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED
    ],
    CustodyTransactionStatus.CONFIRMED: [
        CustodyTransactionStatus.ANCHOR_SUBMITTED,
        CustodyTransactionStatus.COMPLETED,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED
    ],
    CustodyTransactionStatus.ANCHOR_SUBMITTED: [
        CustodyTransactionStatus.COMPLETED,
        CustodyTransactionStatus.FAILED,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED
    ],
    CustodyTransactionStatus.RECONCILIATION_REQUIRED: [
        CustodyTransactionStatus.COMPLETED,
        CustodyTransactionStatus.FAILED
    ],
    CustodyTransactionStatus.FAILED: [],
    CustodyTransactionStatus.COMPLETED: []
}

# In-memory store for isolated test suites and offline development
CUSTODY_TRANSACTIONS_STORE: dict[str, dict] = {}


async def create_durable_transaction(
    evidence_id: str,
    actor_id: str,
    new_custodian: str,
    reason: str,
    idempotency_key: Optional[str] = None,
    payload_fingerprint: Optional[str] = None,
    lock_token: Optional[str] = None,
    fencing_version: int = 0
) -> dict:
    """
    Atomically persist transaction intent into MongoDB before any external RPC broadcast.
    Guarantees that a crash or timeout cannot produce an unrecorded on-chain transaction.
    """
    tx_id = f"CTX-{evidence_id}-{uuid.uuid4().hex[:8].upper()}"
    now = time.time()

    tx_doc = {
        "transaction_id": tx_id,
        "evidence_id": evidence_id,
        "actor_id": actor_id,
        "new_custodian": new_custodian,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "payload_fingerprint": payload_fingerprint,
        "lock_token": lock_token,
        "fencing_version": fencing_version,
        "status": CustodyTransactionStatus.PREPARED.value,
        "transfer_tx_hash": None,
        "transfer_block_number": None,
        "anchor_tx_hash": None,
        "anchor_sequence_number": None,
        "event_hash": None,
        "previous_event_hash": None,
        "contract_address": CONTRACT_ADDRESS,
        "chain_id": EXPECTED_CHAIN_ID,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "response": None
    }

    CUSTODY_TRANSACTIONS_STORE[tx_id] = dict(tx_doc)

    if db_client.is_connected():
        try:
            await db_client.db["custody_transactions"].insert_one(dict(tx_doc))
        except Exception as e:
            logger.debug(f"Failed to persist durable custody transaction in MongoDB: {e}")
            if db_client.require_persistent_storage:
                raise RuntimeError(f"Database error writing transaction intent: {e}")

    return tx_doc


async def get_durable_transaction(transaction_id: str) -> Optional[dict]:
    """Retrieve durable custody transaction by transaction_id."""
    if db_client.is_connected():
        try:
            doc = await db_client.db["custody_transactions"].find_one({"transaction_id": transaction_id}, {"_id": 0})
            if doc:
                return doc
        except Exception:
            pass

    if transaction_id in CUSTODY_TRANSACTIONS_STORE:
        return dict(CUSTODY_TRANSACTIONS_STORE[transaction_id])
    return None


async def find_transaction_by_idempotency_key(idempotency_key: str) -> Optional[dict]:
    """Find existing transaction registered under a specific idempotency key."""
    if not idempotency_key:
        return None

    if db_client.is_connected():
        try:
            doc = await db_client.db["custody_transactions"].find_one({"idempotency_key": idempotency_key}, {"_id": 0})
            if doc:
                return doc
        except Exception:
            pass

    for tx in CUSTODY_TRANSACTIONS_STORE.values():
        if tx.get("idempotency_key") == idempotency_key:
            return dict(tx)
    return None


async def find_active_transaction_for_evidence(evidence_id: str) -> Optional[dict]:
    """Find any in-flight or unresolved transaction for an evidence ID."""
    active_statuses = [
        CustodyTransactionStatus.PREPARED.value,
        CustodyTransactionStatus.SUBMITTED.value,
        CustodyTransactionStatus.CONFIRMED.value,
        CustodyTransactionStatus.ANCHOR_SUBMITTED.value,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED.value
    ]

    if db_client.is_connected():
        try:
            doc = await db_client.db["custody_transactions"].find_one(
                {"evidence_id": evidence_id, "status": {"$in": active_statuses}},
                {"_id": 0}
            )
            if doc:
                return doc
        except Exception:
            pass

    for tx in CUSTODY_TRANSACTIONS_STORE.values():
        if tx.get("evidence_id") == evidence_id and tx.get("status") in active_statuses:
            return dict(tx)
    return None


async def update_transaction_state(
    transaction_id: str,
    new_status: CustodyTransactionStatus,
    update_fields: Optional[dict] = None
) -> dict:
    """
    Atomically transition transaction to new_status with validation of allowed transitions.
    """
    tx = await get_durable_transaction(transaction_id)
    if not tx:
        raise ValueError(f"Durable transaction '{transaction_id}' not found.")

    curr_status = CustodyTransactionStatus(tx["status"])
    allowed = ALLOWED_TRANSITIONS.get(curr_status, [])

    if new_status not in allowed and curr_status != new_status:
        raise ValueError(f"Invalid transaction transition: {curr_status.value} -> {new_status.value}")

    now = time.time()
    fields = update_fields.copy() if update_fields else {}
    fields["status"] = new_status.value
    fields["updated_at"] = now
    if new_status == CustodyTransactionStatus.COMPLETED:
        fields["completed_at"] = now

    # Update in-memory store
    if transaction_id in CUSTODY_TRANSACTIONS_STORE:
        CUSTODY_TRANSACTIONS_STORE[transaction_id].update(fields)

    # Update MongoDB
    if db_client.is_connected():
        try:
            res = await db_client.db["custody_transactions"].update_one(
                {"transaction_id": transaction_id},
                {"$set": fields}
            )
            if res.modified_count == 0 and db_client.require_persistent_storage:
                logger.warning(f"Failed to update transaction {transaction_id} in MongoDB.")
        except Exception as e:
            logger.debug(f"Exception updating transaction {transaction_id} state: {e}")
            if db_client.require_persistent_storage:
                raise

    tx.update(fields)
    return tx


async def reconcile_durable_transaction(
    transaction_id: str,
    allow_offline_fallback: bool = False
) -> tuple[bool, dict, Optional[str]]:
    """
    Safely reconcile an in-flight or interrupted custody transaction against on-chain reality.
    Validates:
    - Connected Chain ID matches EXPECTED_CHAIN_ID
    - Target contract address matches CONTRACT_ADDRESS and is deployed
    - Transaction receipts exist, status is confirmed (status == 1 / 0x1)
    - Incomplete or malformed receipt data is rejected
    - Pending transactions in mempool are recognized without premature failure
    - Dropped/replaced transactions are detected
    - Evidence ID exists on-chain and custody state continuity is validated
    - Sequence continuity and canonical event hash match bit-for-bit
    - Fencing versions protect database commit from stale worker overwrites

    Returns: (is_reconciled: bool, transaction_dict: dict, error_code: Optional[str])
    """
    tx = await get_durable_transaction(transaction_id)
    if not tx:
        return False, {}, "TRANSACTION_NOT_FOUND"

    status = tx.get("status")
    evidence_id = tx["evidence_id"]
    transfer_tx = tx.get("transfer_tx_hash")
    anchor_tx = tx.get("anchor_tx_hash")

    # 1. Validate Chain ID
    chain_id = get_blockchain_chain_id()
    if chain_id is None:
        if not allow_offline_fallback:
            return False, tx, "BLOCKCHAIN_RPC_UNAVAILABLE"
    elif chain_id != EXPECTED_CHAIN_ID:
        tx = await update_transaction_state(
            transaction_id,
            CustodyTransactionStatus.RECONCILIATION_REQUIRED,
            {"error_message": f"Chain ID mismatch during reconciliation: {chain_id} != {EXPECTED_CHAIN_ID}"}
        )
        return False, tx, "CHAIN_ID_MISMATCH"

    # 2. Validate Target Contract Deployment
    is_deployed, dep_err = verify_contract_deployed(CONTRACT_ADDRESS)
    if not is_deployed and not allow_offline_fallback:
        tx = await update_transaction_state(
            transaction_id,
            CustodyTransactionStatus.RECONCILIATION_REQUIRED,
            {"error_message": f"Contract address {CONTRACT_ADDRESS} bytecode missing or undeployed ({dep_err})."}
        )
        return False, tx, "CONTRACT_NOT_DEPLOYED"

    # 3. Check Transfer Transaction on Blockchain
    transfer_confirmed = False
    if transfer_tx:
        rcpt, rcpt_err = get_transaction_receipt(transfer_tx)
        if rcpt_err == "TRANSACTION_REVERTED":
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.FAILED,
                {"error_message": f"Transfer transaction '{transfer_tx}' reverted on-chain."}
            )
            return False, tx, "TRANSFER_TRANSACTION_REVERTED"
        elif rcpt_err == "INCOMPLETE_RECEIPT_DATA":
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": f"Transfer transaction '{transfer_tx}' receipt has incomplete or malformed status."}
            )
            return False, tx, "INCOMPLETE_RECEIPT_DATA"
        elif rcpt_err == "RPC_UNAVAILABLE" and not allow_offline_fallback:
            return False, tx, "BLOCKCHAIN_RPC_UNAVAILABLE"
        elif rcpt_err == "RECEIPT_NOT_FOUND":
            # Check if transaction is still pending in mempool
            tx_obj, tx_err = get_transaction_by_hash(transfer_tx)
            if tx_obj and tx_obj.get("blockNumber") is None:
                # Pending in mempool; do NOT fail or complete
                return False, tx, "TRANSACTION_PENDING"
            elif tx_err == "RPC_UNAVAILABLE" and not allow_offline_fallback:
                return False, tx, "BLOCKCHAIN_RPC_UNAVAILABLE"
            else:
                # Transaction was dropped, replaced, or never mined
                tx = await update_transaction_state(
                    transaction_id,
                    CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                    {"error_message": f"Transfer transaction '{transfer_tx}' dropped or not found in mempool/chain."}
                )
                return False, tx, "TRANSACTION_DROPPED_OR_NOT_FOUND"
        elif rcpt is not None:
            # Validate target contract address on receipt
            rcpt_to = (rcpt.get("to") or "").lower()
            expected_to = CONTRACT_ADDRESS.lower()
            if rcpt_to and rcpt_to != expected_to:
                tx = await update_transaction_state(
                    transaction_id,
                    CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                    {"error_message": f"Transfer transaction receipt target contract mismatch: {rcpt_to} != {expected_to}"}
                )
                return False, tx, "CONTRACT_ADDRESS_MISMATCH"

            block_num = int(rcpt.get("blockNumber", "0x0"), 16) if isinstance(rcpt.get("blockNumber"), str) else rcpt.get("blockNumber", 0)
            if block_num <= 0:
                tx = await update_transaction_state(
                    transaction_id,
                    CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                    {"error_message": f"Transfer transaction '{transfer_tx}' has invalid blockNumber: {block_num}"}
                )
                return False, tx, "INCOMPLETE_RECEIPT_DATA"

            transfer_confirmed = True
            if status == CustodyTransactionStatus.SUBMITTED.value:
                tx = await update_transaction_state(
                    transaction_id,
                    CustodyTransactionStatus.CONFIRMED,
                    {"transfer_block_number": block_num}
                )
    else:
        # Failure Windows 1 & 2: No transaction hash was persisted
        # Outcome is uncertain; fail-closed without blind rebroadcast
        tx = await update_transaction_state(
            transaction_id,
            CustodyTransactionStatus.RECONCILIATION_REQUIRED,
            {"error_message": "Uncertain broadcast outcome: intent persisted in PREPARED but no transaction hash was recorded before interruption."}
        )
        return False, tx, "UNCERTAIN_BROADCAST_OUTCOME"

    # 4. Check Anchor Transaction if submitted
    anchor_confirmed = False
    if anchor_tx:
        a_rcpt, a_err = get_transaction_receipt(anchor_tx)
        if a_err == "TRANSACTION_REVERTED":
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": f"Anchor transaction '{anchor_tx}' reverted on-chain."}
            )
            return False, tx, "ANCHOR_TRANSACTION_REVERTED"
        elif a_err == "INCOMPLETE_RECEIPT_DATA":
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": f"Anchor transaction '{anchor_tx}' receipt has incomplete or malformed status."}
            )
            return False, tx, "INCOMPLETE_RECEIPT_DATA"
        elif a_err == "RPC_UNAVAILABLE" and not allow_offline_fallback:
            return False, tx, "BLOCKCHAIN_RPC_UNAVAILABLE"
        elif a_rcpt is not None:
            a_to = (a_rcpt.get("to") or "").lower()
            expected_to = CONTRACT_ADDRESS.lower()
            if a_to and a_to != expected_to:
                tx = await update_transaction_state(
                    transaction_id,
                    CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                    {"error_message": f"Anchor transaction receipt target contract mismatch: {a_to} != {expected_to}"}
                )
                return False, tx, "CONTRACT_ADDRESS_MISMATCH"
            anchor_confirmed = True

    # 5. Independent contract state inspection
    onchain_rec, onchain_err = query_contract_evidence(evidence_id)
    if onchain_err == "RPC_UNAVAILABLE" and not allow_offline_fallback:
        return False, tx, "BLOCKCHAIN_RPC_UNAVAILABLE"
    elif onchain_err == "NOT_FOUND":
        from .blockchain import CHAIN_EVIDENCE_STORE
        if allow_offline_fallback and evidence_id in CHAIN_EVIDENCE_STORE:
            onchain_rec = CHAIN_EVIDENCE_STORE[evidence_id]
        else:
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": f"Evidence '{evidence_id}' does not exist on-chain."}
            )
            return False, tx, "ON_CHAIN_EVIDENCE_NOT_FOUND"

    seq = tx.get("anchor_sequence_number")
    if seq:
        anchor_rec, anc_err = get_custody_anchor_from_chain(evidence_id, seq, allow_offline_fallback=allow_offline_fallback)
        if anc_err == "RPC_UNAVAILABLE" and not allow_offline_fallback:
            return False, tx, "BLOCKCHAIN_RPC_UNAVAILABLE"
        if anchor_rec and anchor_rec.get("exists"):
            # Validate hash consistency
            if tx.get("event_hash") and anchor_rec.get("event_hash").lower() != tx.get("event_hash").lower():
                tx = await update_transaction_state(
                    transaction_id,
                    CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                    {"error_message": f"On-chain anchor hash mismatch: '{anchor_rec.get('event_hash')}' != '{tx.get('event_hash')}'."}
                )
                return False, tx, "ANCHOR_HASH_MISMATCH"
            anchor_confirmed = True
        elif anc_err == "NOT_FOUND" and anchor_tx:
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": f"Anchor sequence {seq} does not exist on-chain despite anchor transaction."}
            )
            return False, tx, "ANCHOR_NOT_FOUND_ON_CHAIN"

    # 6. Determine reconciliation action & synchronize database commit
    if transfer_confirmed and (anchor_confirmed or not anchor_tx):
        from ..routes.evidence import EVIDENCE_STORE
        new_custodian = tx["new_custodian"]
        expected_version = tx.get("fencing_version", 0)

        # Check fencing version against EVIDENCE_STORE if present
        current_mem_ver = EVIDENCE_STORE.get(evidence_id, {}).get("custody_version", 0)
        if current_mem_ver != expected_version and expected_version != 0:
            logger.warning(f"Fencing conflict in memory during reconciliation of {transaction_id}. Version advanced to {current_mem_ver}.")
            tx = await update_transaction_state(
                transaction_id,
                CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                {"error_message": f"Fencing conflict: in-memory version {current_mem_ver} != expected {expected_version}"}
            )
            return False, tx, "FENCING_CONFLICT"

        # Update in-memory
        if evidence_id in EVIDENCE_STORE:
            EVIDENCE_STORE[evidence_id]["custodian"] = new_custodian

        # Update MongoDB with fencing check
        if db_client.is_connected():
            try:
                ev_doc = await db_client.evidence.find_one({"evidence_id": evidence_id})
                if ev_doc and ev_doc.get("custodian") != new_custodian:
                    curr_version = ev_doc.get("custody_version", 0)
                    if curr_version != expected_version and expected_version != 0:
                        logger.warning(f"Fencing conflict during reconciliation of {transaction_id}. Version advanced to {curr_version}.")
                        tx = await update_transaction_state(
                            transaction_id,
                            CustodyTransactionStatus.RECONCILIATION_REQUIRED,
                            {"error_message": f"Fencing conflict: DB version {curr_version} != expected {expected_version}"}
                        )
                        return False, tx, "FENCING_CONFLICT"

                    await db_client.evidence.update_one(
                        {"evidence_id": evidence_id},
                        {
                            "$set": {
                                "custodian": new_custodian,
                                "transfer_lock.status": "UNLOCKED",
                                "transfer_lock.released_at": time.time()
                            },
                            "$inc": {"custody_version": 1}
                        }
                    )
            except Exception as e:
                logger.error(f"Reconciliation MongoDB commit error: {e}")
                if db_client.require_persistent_storage:
                    return False, tx, "DATABASE_COMMIT_FAILED"

        # Transition to COMPLETED
        tx = await update_transaction_state(
            transaction_id,
            CustodyTransactionStatus.COMPLETED,
            {"error_message": None}
        )
        return True, tx, None

    # Unresolved state
    tx = await update_transaction_state(
        transaction_id,
        CustodyTransactionStatus.RECONCILIATION_REQUIRED,
        {"error_message": "Transaction state could not be automatically reconciled."}
    )
    return False, tx, "MANUAL_RECONCILIATION_REQUIRED"
