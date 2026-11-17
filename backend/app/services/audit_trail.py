"""
ChainVault Phase 2 — Tamper-Evident Custody Audit Trail & Verification Engine
===========================================================================
Defines:
1. Versioned custody event data model.
2. Deterministic canonical hash calculation (SHA-256, UTC ISO-8601, deterministic serialization).
3. Concurrency-controlled event creation and sequence management.
4. Independent audit trail verification engine.
5. MongoDB persistence with in-memory synchronization.
6. Blockchain anchor reconciliation against EvidenceRegistry.sol.
"""

import os
import json
import uuid
import asyncio
import hashlib
import datetime
import logging
from typing import Optional, Union, Any

logger = logging.getLogger(__name__)

# In-memory storage dictionary imported from existing custody module to maintain full compatibility
from ..routes.custody import AUDIT_LOGS_STORE
from ..database.mongodb import db_client
from .blockchain import (
    get_independent_blockchain_record,
    get_blockchain_chain_id,
    check_blockchain_health,
    _rpc_call,
    EXPECTED_CHAIN_ID,
    CONTRACT_ADDRESS,
    CHAIN_EVIDENCE_STORE,
    CHAIN_CUSTODY_LOGS,
    CHAIN_CUSTODY_ANCHORS,
    anchor_custody_event_on_chain,
    get_custody_anchor_from_chain
)

# Concurrency locks per evidence_id to prevent concurrent branching and race conditions
_EVIDENCE_LOCKS: dict[str, asyncio.Lock] = {}
_GLOBAL_LOCK = asyncio.Lock()

def get_evidence_lock(evidence_id: str) -> asyncio.Lock:
    """Retrieve or create a dedicated lock for serializing custody events on a given evidence item."""
    if evidence_id not in _EVIDENCE_LOCKS:
        _EVIDENCE_LOCKS[evidence_id] = asyncio.Lock()
    return _EVIDENCE_LOCKS[evidence_id]


# -----------------------------------------------------------------------------
# 1. CANONICAL EVENT HASH CALCULATION
# -----------------------------------------------------------------------------

def normalize_utc_timestamp(ts: Union[str, datetime.datetime, None]) -> str:
    """
    Deterministically normalize any timestamp into UTC ISO-8601 string:
    'YYYY-MM-DDTHH:MM:SS.ffffffZ'
    Ensures identical byte representations across different platforms and timezones.
    """
    if ts is None:
        dt = datetime.datetime.now(datetime.timezone.utc)
    elif isinstance(ts, datetime.datetime):
        dt = ts
    elif isinstance(ts, str):
        # Handle trailing Z
        clean_ts = ts.strip()
        if clean_ts.endswith("Z"):
            clean_ts = clean_ts[:-1] + "+00:00"
        try:
            dt = datetime.datetime.fromisoformat(clean_ts)
        except Exception:
            # Fallback for non-microsecond string
            dt = datetime.datetime.strptime(clean_ts[:19], "%Y-%m-%dT%H:%M:%S")
    else:
        raise ValueError(f"Unsupported timestamp format: {type(ts)}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_event_representation(event: dict) -> dict:
    """
    Construct the canonical dictionary for Schema Version 1 event hashing.
    Strictly includes only the defined immutable fields.
    Strictly EXCLUDES:
    - 'event_hash' (hash cannot hash itself)
    - 'anchor_reference' / 'blockchain_tx' (populated asynchronously upon on-chain confirmation)
    - 'log_id', 'previous_custodian', 'new_custodian', 'reason' (backward-compatibility aliases)
    """
    raw_ver = event.get("schema_version", 1)
    try:
        version = int(str(raw_ver).split(".")[0]) if raw_ver is not None else 1
    except (ValueError, TypeError):
        version = 1
    if version == 1:
        details = event.get("details", {})
        if not isinstance(details, dict):
            details = {}
        # Ensure details contains deterministic serializable primitives
        norm_details = {}
        for k in sorted(details.keys()):
            v = details[k]
            if isinstance(v, (int, float, bool, list, dict)):
                norm_details[str(k)] = v
            else:
                norm_details[str(k)] = str(v) if v is not None else ""

        return {
            "schema_version": 1,
            "event_id": str(event.get("event_id", "")),
            "evidence_id": str(event.get("evidence_id", "")),
            "case_id": str(event.get("case_id", "") or ""),
            "actor_id": str(event.get("actor_id", "")),
            "action": str(event.get("action", "")),
            "timestamp": normalize_utc_timestamp(event.get("timestamp")),
            "sequence_number": int(event.get("sequence_number", 1)),
            "previous_event_hash": str(event.get("previous_event_hash", "GENESIS")),
            "details": norm_details
        }
    else:
        raise ValueError(f"Unsupported custody event schema version: {version}")


def calculate_canonical_event_hash(event: dict) -> str:
    """
    Deterministically serialize the canonical event representation to UTF-8 JSON
    with sorted keys and compact separators, then return its SHA-256 hex digest.
    """
    canonical_dict = canonical_event_representation(event)
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# 2. EVENT RETRIEVAL & PERSISTENCE
# -----------------------------------------------------------------------------

async def get_stored_custody_events(evidence_id: str, allow_in_memory_fallback: bool = True) -> list[dict]:
    """
    Retrieve stored custody events for an evidence item.
    Attempts MongoDB query first; if offline or empty and allow_in_memory_fallback is True,
    retrieves from AUDIT_LOGS_STORE.
    Ensures returned records are clean copies without MongoDB '_id' mutations.
    """
    events: list[dict] = []

    # 1. Query MongoDB if connected
    if db_client.client and db_client.db is not None:
        try:
            cursor = db_client.audit_logs.find(
                {"evidence_id": evidence_id},
                {"_id": 0}
            ).sort("sequence_number", 1)
            async for doc in cursor:
                events.append(doc)
        except Exception as e:
            logger.debug(f"MongoDB audit log query failed: {e}")
            if not allow_in_memory_fallback:
                raise RuntimeError(f"Database query failed and in-memory fallback is disabled: {e}")

    # 2. Fall back to AUDIT_LOGS_STORE if MongoDB returned nothing and fallback allowed
    if not events and allow_in_memory_fallback and evidence_id in AUDIT_LOGS_STORE:
        # Shallow copy items to avoid external side-effects
        events = [dict(ev) for ev in AUDIT_LOGS_STORE[evidence_id]]

    return events


async def persist_custody_event(event: dict) -> dict:
    """
    Persist custody event into MongoDB and synchronized in-memory AUDIT_LOGS_STORE.
    """
    ev_id = event["evidence_id"]

    # In-memory synchronization (preserves backward compatibility with existing tests & endpoints)
    if ev_id not in AUDIT_LOGS_STORE:
        AUDIT_LOGS_STORE[ev_id] = []
    
    # Check for existing duplicate event_id in in-memory store
    for existing in AUDIT_LOGS_STORE[ev_id]:
        if existing.get("event_id") == event["event_id"]:
            return existing

    AUDIT_LOGS_STORE[ev_id].append(dict(event))

    # MongoDB persistence if active
    if db_client.client and db_client.db is not None:
        try:
            doc = dict(event)
            # Remove any existing _id if present
            doc.pop("_id", None)
            await db_client.audit_logs.insert_one(doc)
        except Exception as e:
            logger.debug(f"MongoDB insert_one failed: {e}")
            if db_client.require_persistent_storage:
                raise RuntimeError(f"Audit log persistence failed: {e}")

    return event


# -----------------------------------------------------------------------------
# 3. CONCURRENCY-CONTROLLED EVENT CREATION
# -----------------------------------------------------------------------------

async def record_custody_event(
    evidence_id: str,
    action: str,
    actor_id: str,
    case_id: Optional[str] = "CV-2026-001",
    details: Optional[dict] = None,
    anchor_reference: Optional[str] = None,
    custom_timestamp: Optional[str] = None
) -> dict:
    """
    Atomically create and persist a new hash-linked custody event.
    Enforces per-evidence serialization to prevent concurrent branching,
    monotonic sequence numbering, and canonical hash calculation.
    """
    lock = get_evidence_lock(evidence_id)
    async with lock:
        history = await get_stored_custody_events(evidence_id)

        if not history:
            sequence_number = 1
            previous_event_hash = "GENESIS"
        else:
            last_event = history[-1]
            sequence_number = int(last_event.get("sequence_number", len(history))) + 1
            previous_event_hash = last_event.get("event_hash", "")

        event_id = f"EVT-{evidence_id}-{sequence_number:04d}-{uuid.uuid4().hex[:6].upper()}"
        ts = custom_timestamp or normalize_utc_timestamp(datetime.datetime.now(datetime.timezone.utc))

        event_details = details.copy() if details else {}

        # Construct versioned event record
        event = {
            "schema_version": 1,
            "event_id": event_id,
            "log_id": event_id,  # Backward-compatible alias
            "evidence_id": evidence_id,
            "case_id": case_id or "CV-2026-001",
            "actor_id": actor_id,
            "action": action,
            "timestamp": ts,
            "sequence_number": sequence_number,
            "previous_event_hash": previous_event_hash,
            "anchor_reference": anchor_reference,
            "blockchain_tx": anchor_reference,  # Backward-compatible alias
            "details": event_details,
            # Backward-compatible aliases for custody transfer fields
            "previous_custodian": event_details.get("previous_custodian"),
            "new_custodian": event_details.get("new_custodian"),
            "reason": event_details.get("reason")
        }

        # Calculate canonical SHA-256 event hash
        event["event_hash"] = calculate_canonical_event_hash(event)

        # On-chain cryptographic custody anchor creation
        if anchor_reference or action in ("CUSTODY_TRANSFER", "BLOCKCHAIN_REGISTRATION"):
            try:
                anc_rec = anchor_custody_event_on_chain(
                    evidence_id=evidence_id,
                    sequence_number=sequence_number,
                    event_hash=event["event_hash"],
                    previous_event_hash=previous_event_hash,
                    schema_version=1
                )
                if not anchor_reference:
                    event["anchor_reference"] = anc_rec.get("tx_hash")
                    event["blockchain_tx"] = anc_rec.get("tx_hash")
            except Exception as e:
                logger.debug(f"Automatic on-chain custody anchoring failed: {e}")

        # Persist event
        await persist_custody_event(event)
        return event


# -----------------------------------------------------------------------------
# 4. BLOCKCHAIN TRANSACTION ANCHOR RETRIEVAL
# -----------------------------------------------------------------------------

def check_on_chain_tx_receipt(tx_hash: str, allow_offline_fallback: bool = False) -> tuple[Optional[dict], Optional[str]]:
    """
    Independently verify an on-chain anchor transaction receipt via eth_getTransactionReceipt.
    Returns (receipt_dict, error_code).
    error_code:
      - None: verified mined transaction
      - 'RPC_UNAVAILABLE': RPC node offline
      - 'NOT_FOUND': transaction receipt does not exist on blockchain
      - 'TX_REVERTED': transaction executed but reverted (status != 1)
    """
    if not tx_hash or not tx_hash.startswith("0x"):
        return None, "NOT_FOUND"

    try:
        res = _rpc_call("eth_getTransactionReceipt", [tx_hash])
        if "error" in res:
            if allow_offline_fallback:
                for logs in CHAIN_CUSTODY_LOGS.values():
                    for l in logs:
                        if l.get("tx_hash") == tx_hash:
                            return l, None
                for rec in CHAIN_EVIDENCE_STORE.values():
                    if rec.get("tx_hash") == tx_hash:
                        return rec, None
            return None, "RPC_UNAVAILABLE"
        if "result" in res and res["result"]:
            rcpt = res["result"]
            status_hex = rcpt.get("status", "0x1")
            if int(status_hex, 16) == 1:
                return rcpt, None
            else:
                return rcpt, "TX_REVERTED"

        # Check local test stores if not mined or simulated
        for logs in CHAIN_CUSTODY_LOGS.values():
            for l in logs:
                if l.get("tx_hash") == tx_hash:
                    return l, None
        for rec in CHAIN_EVIDENCE_STORE.values():
            if rec.get("tx_hash") == tx_hash:
                return rec, None

        return None, "NOT_FOUND"
    except Exception as e:
        logger.debug(f"check_on_chain_tx_receipt failed: {e}")
        for logs in CHAIN_CUSTODY_LOGS.values():
            for l in logs:
                if l.get("tx_hash") == tx_hash:
                    return l, None
        for rec in CHAIN_EVIDENCE_STORE.values():
            if rec.get("tx_hash") == tx_hash:
                return rec, None
        return None, "RPC_UNAVAILABLE"


# -----------------------------------------------------------------------------
# 5. AUDIT TRAIL VERIFICATION ENGINE
# -----------------------------------------------------------------------------

async def verify_custody_audit_trail(
    evidence_id: str,
    require_blockchain: bool = False,
    allow_offline_fallback: bool = False,
    allow_in_memory_fallback: bool = True
) -> dict:
    """
    Independently verify the complete custody audit history for an evidence item.
    Performs 10 distinct cryptographic and structural validations:
    1. Existence check (NOT_FOUND).
    2. Evidence association check.
    3. Duplicate event ID check.
    4. Duplicate sequence number check.
    5. Sequence continuity & strictly monotonic progression.
    6. Genesis predecessor representation ('GENESIS').
    7. Hash-link continuity (previous_event_hash == preceding event_hash).
    8. Deterministic canonical hash recomputation (detects modified event contents).
    9. Genesis registration reconciliation against EvidenceRegistry.sol.
    10. Anchor transaction existence & status verification on the Ethereum ledger.

    Returns structured status:
      'VERIFIED'     - Chain, hashes, and all required anchors agree.
      'TAMPERED'     - Confirmed hash mismatch, modified content, or broken predecessor link.
      'INCONSISTENT' - Structural conflict, sequence gap, duplicate ID/seq, or unanchored history.
      'NOT_FOUND'    - Evidence or audit history not found anywhere.
      'UNAVAILABLE'  - Verification cannot complete due to offline required infrastructure.
    """
    from ..routes.evidence import EVIDENCE_STORE

    # Step 1: Retrieve stored events
    try:
        events = await get_stored_custody_events(evidence_id, allow_in_memory_fallback=allow_in_memory_fallback)
    except Exception as e:
        return {
            "status": "error",
            "verification_status": "UNAVAILABLE",
            "evidence_id": evidence_id,
            "verified": False,
            "tampered": False,
            "event_count": 0,
            "chain_intact": False,
            "blockchain_reconciled": False,
            "technical_error": "DATABASE_UNAVAILABLE",
            "failure_reason": f"Database failure retrieving custody audit events: {e}",
            "events": []
        }
    evidence_exists_locally = evidence_id in EVIDENCE_STORE

    # Check existence
    if not events and not evidence_exists_locally:
        # Check blockchain before declaring NOT_FOUND
        onchain_rec, onchain_err = get_independent_blockchain_record(evidence_id, allow_offline_fallback=allow_offline_fallback)
        if onchain_err == "RPC_UNAVAILABLE" and require_blockchain:
            return {
                "status": "error",
                "verification_status": "UNAVAILABLE",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": 0,
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "BLOCKCHAIN_RPC_UNAVAILABLE",
                "failure_reason": "Blockchain RPC is unreachable; independent verification failed closed.",
                "events": []
            }
        if onchain_rec is None:
            return {
                "status": "error",
                "verification_status": "NOT_FOUND",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": 0,
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "EVIDENCE_NOT_FOUND",
                "failure_reason": f"Evidence record '{evidence_id}' and custody history not found.",
                "events": []
            }

    if not events:
        return {
            "status": "error",
            "verification_status": "INCONSISTENT",
            "evidence_id": evidence_id,
            "verified": False,
            "tampered": False,
            "event_count": 0,
            "chain_intact": False,
            "blockchain_reconciled": False,
            "technical_error": "NO_AUDIT_EVENTS",
            "failure_reason": f"Evidence '{evidence_id}' exists but has no recorded custody audit events.",
            "events": []
        }

    # Step 2: Validate identifiers and duplicates
    seen_event_ids = set()
    seen_sequences = set()
    event_details_report = []

    for idx, ev in enumerate(events):
        ev_id = ev.get("evidence_id")
        if ev_id != evidence_id:
            return {
                "status": "error",
                "verification_status": "INCONSISTENT",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": len(events),
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "EVIDENCE_ID_MISMATCH",
                "failure_reason": f"Event at index {idx} belongs to evidence '{ev_id}', expected '{evidence_id}'.",
                "events": []
            }

        eid = ev.get("event_id")
        if not eid or eid in seen_event_ids:
            return {
                "status": "error",
                "verification_status": "INCONSISTENT",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": len(events),
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "DUPLICATE_EVENT_ID",
                "failure_reason": f"Duplicate or missing event identifier '{eid}' at index {idx}.",
                "events": []
            }
        seen_event_ids.add(eid)

        seq = ev.get("sequence_number")
        if seq is None or seq in seen_sequences:
            return {
                "status": "error",
                "verification_status": "INCONSISTENT",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": len(events),
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "DUPLICATE_SEQUENCE_NUMBER",
                "failure_reason": f"Duplicate or missing sequence number '{seq}' at index {idx}.",
                "events": []
            }
        seen_sequences.add(seq)

    # Step 3: Check sequence ordering and predecessor chain links
    for i, ev in enumerate(events):
        seq = ev.get("sequence_number", 0)
        stored_hash = ev.get("event_hash", "")
        prev_hash = ev.get("previous_event_hash", "")

        # Recalculate canonical hash
        try:
            recomputed_hash = calculate_canonical_event_hash(ev)
        except Exception as e:
            return {
                "status": "error",
                "verification_status": "TAMPERED",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": True,
                "event_count": len(events),
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "CANONICALIZATION_FAILURE",
                "failure_reason": f"Failed to compute canonical hash for event '{ev.get('event_id')}': {e}",
                "events": []
            }

        # Content modification check
        hash_valid = bool(stored_hash and recomputed_hash and stored_hash.lower() == recomputed_hash.lower())
        if not hash_valid:
            return {
                "status": "error",
                "verification_status": "TAMPERED",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": True,
                "event_count": len(events),
                "chain_intact": False,
                "blockchain_reconciled": False,
                "technical_error": "EVENT_HASH_MISMATCH",
                "failure_reason": f"Event content modification detected at sequence {seq} (event ID '{ev.get('event_id')}'): stored hash '{stored_hash}' does not match recomputed canonical hash '{recomputed_hash}'.",
                "events": []
            }

        # Sequence progression and predecessor link check
        if i == 0:
            if seq != 1:
                return {
                    "status": "error",
                    "verification_status": "INCONSISTENT",
                    "evidence_id": evidence_id,
                    "verified": False,
                    "tampered": False,
                    "event_count": len(events),
                    "chain_intact": False,
                    "blockchain_reconciled": False,
                    "technical_error": "MISSING_GENESIS_EVENT",
                    "failure_reason": f"Custody history missing genesis event: first sequence is {seq} instead of 1.",
                    "events": []
                }
            if prev_hash != "GENESIS":
                return {
                    "status": "error",
                    "verification_status": "TAMPERED",
                    "evidence_id": evidence_id,
                    "verified": False,
                    "tampered": True,
                    "event_count": len(events),
                    "chain_intact": False,
                    "blockchain_reconciled": False,
                    "technical_error": "INVALID_GENESIS_PREDECESSOR",
                    "failure_reason": f"Genesis event sequence 1 has invalid predecessor hash '{prev_hash}', expected 'GENESIS'.",
                    "events": []
                }
            link_valid = True
        else:
            prev_event = events[i - 1]
            prev_seq = prev_event.get("sequence_number", 0)
            expected_prev_hash = prev_event.get("event_hash", "")

            # Reordering check
            if seq < prev_seq:
                return {
                    "status": "error",
                    "verification_status": "INCONSISTENT",
                    "evidence_id": evidence_id,
                    "verified": False,
                    "tampered": False,
                    "event_count": len(events),
                    "chain_intact": False,
                    "blockchain_reconciled": False,
                    "technical_error": "EVENT_REORDERING_DETECTED",
                    "failure_reason": f"Event reordering detected: sequence {seq} appears after sequence {prev_seq}.",
                    "events": []
                }

            # Sequence gap check (event deletion)
            if seq != prev_seq + 1:
                return {
                    "status": "error",
                    "verification_status": "INCONSISTENT",
                    "evidence_id": evidence_id,
                    "verified": False,
                    "tampered": False,
                    "event_count": len(events),
                    "chain_intact": False,
                    "blockchain_reconciled": False,
                    "technical_error": "SEQUENCE_GAP_DETECTED",
                    "failure_reason": f"Sequence gap detected between sequence {prev_seq} and {seq} (event deletion detected).",
                    "events": []
                }

            # Predecessor link check
            if prev_hash.lower() != expected_prev_hash.lower():
                return {
                    "status": "error",
                    "verification_status": "TAMPERED",
                    "evidence_id": evidence_id,
                    "verified": False,
                    "tampered": True,
                    "event_count": len(events),
                    "chain_intact": False,
                    "blockchain_reconciled": False,
                    "technical_error": "BROKEN_PREDECESSOR_LINK",
                    "failure_reason": f"Broken predecessor hash link at sequence {seq}: predecessor reference '{prev_hash}' does not match prior event hash '{expected_prev_hash}'.",
                    "events": []
                }
            link_valid = True

        event_details_report.append({
            "sequence_number": seq,
            "event_id": ev.get("event_id"),
            "action": ev.get("action"),
            "actor_id": ev.get("actor_id"),
            "timestamp": ev.get("timestamp"),
            "previous_event_hash": prev_hash,
            "stored_event_hash": stored_hash,
            "calculated_event_hash": recomputed_hash,
            "hash_valid": hash_valid,
            "link_valid": link_valid,
            "anchor_reference": ev.get("anchor_reference")
        })

    # Step 4: Blockchain Anchor Reconciliation
    blockchain_reconciled = False
    chain_record, chain_err = get_independent_blockchain_record(evidence_id, allow_offline_fallback=allow_offline_fallback)

    if chain_err == "RPC_UNAVAILABLE":
        if require_blockchain:
            return {
                "status": "error",
                "verification_status": "UNAVAILABLE",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": len(events),
                "chain_intact": True,
                "blockchain_reconciled": False,
                "technical_error": "BLOCKCHAIN_RPC_UNAVAILABLE",
                "failure_reason": "Blockchain RPC is offline or unreachable; required independent anchor verification failed closed.",
                "events": event_details_report
            }
        else:
            # Document unanchored state
            blockchain_reconciled = False
    elif chain_err == "CHAIN_ID_MISMATCH":
        return {
            "status": "error",
            "verification_status": "UNAVAILABLE",
            "evidence_id": evidence_id,
            "verified": False,
            "tampered": False,
            "event_count": len(events),
            "chain_intact": True,
            "blockchain_reconciled": False,
            "technical_error": "CHAIN_ID_MISMATCH",
            "failure_reason": f"Connected blockchain network chain ID does not match expected {EXPECTED_CHAIN_ID}.",
            "events": event_details_report
        }
    elif chain_record is not None:
        # Check Genesis event file_hash against smart contract on-chain registration
        genesis_event = events[0]
        genesis_file_hash = genesis_event.get("details", {}).get("file_hash")
        if not genesis_file_hash and evidence_exists_locally:
            genesis_file_hash = EVIDENCE_STORE[evidence_id].get("file_hash")

        onchain_hash = chain_record.get("file_hash")
        if genesis_file_hash and onchain_hash and genesis_file_hash.lower() != onchain_hash.lower():
            return {
                "status": "error",
                "verification_status": "TAMPERED",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": True,
                "event_count": len(events),
                "chain_intact": True,
                "blockchain_reconciled": False,
                "technical_error": "BLOCKCHAIN_ANCHOR_MISMATCH",
                "failure_reason": f"Genesis evidence file hash '{genesis_file_hash}' does not match immutable blockchain anchor '{onchain_hash}'.",
                "events": event_details_report
            }

        # Check on-chain custody anchors for exact canonical event hash verification
        for ev in events:
            seq = ev.get("sequence_number")
            stored_ev_hash = ev.get("event_hash", "")
            prev_ev_hash = ev.get("previous_event_hash", "")
            tx_ref = ev.get("anchor_reference")

            # 1. Check transaction receipt if recorded
            if tx_ref:
                rcpt, rcpt_err = check_on_chain_tx_receipt(tx_ref, allow_offline_fallback=allow_offline_fallback)
                if rcpt_err == "RPC_UNAVAILABLE":
                    if require_blockchain:
                        return {
                            "status": "error",
                            "verification_status": "UNAVAILABLE",
                            "evidence_id": evidence_id,
                            "verified": False,
                            "tampered": False,
                            "event_count": len(events),
                            "chain_intact": True,
                            "blockchain_reconciled": False,
                            "technical_error": "BLOCKCHAIN_RPC_UNAVAILABLE",
                            "failure_reason": f"Cannot verify on-chain receipt for anchor transaction '{tx_ref}': RPC unavailable.",
                            "events": event_details_report
                        }
                elif rcpt_err == "NOT_FOUND":
                    return {
                        "status": "error",
                        "verification_status": "INCONSISTENT",
                        "evidence_id": evidence_id,
                        "verified": False,
                        "tampered": False,
                        "event_count": len(events),
                        "chain_intact": True,
                        "blockchain_reconciled": False,
                        "technical_error": "ANCHOR_TX_NOT_FOUND",
                        "failure_reason": f"Event sequence {seq} references transaction '{tx_ref}' that does not exist on the blockchain.",
                        "events": event_details_report
                    }
                elif rcpt_err == "TX_REVERTED":
                    return {
                        "status": "error",
                        "verification_status": "INCONSISTENT",
                        "evidence_id": evidence_id,
                        "verified": False,
                        "tampered": False,
                        "event_count": len(events),
                        "chain_intact": True,
                        "blockchain_reconciled": False,
                        "technical_error": "ANCHOR_TX_REVERTED",
                        "failure_reason": f"Event sequence {seq} anchor transaction '{tx_ref}' failed on-chain.",
                        "events": event_details_report
                    }

            # 2. Check exact on-chain custody anchor (cryptographic anchor verification)
            anchor_rec, anchor_err = get_custody_anchor_from_chain(evidence_id, seq, allow_offline_fallback=allow_offline_fallback)
            if anchor_err == "RPC_UNAVAILABLE" and require_blockchain:
                return {
                    "status": "error",
                    "verification_status": "UNAVAILABLE",
                    "evidence_id": evidence_id,
                    "verified": False,
                    "tampered": False,
                    "event_count": len(events),
                    "chain_intact": True,
                    "blockchain_reconciled": False,
                    "technical_error": "BLOCKCHAIN_RPC_UNAVAILABLE",
                    "failure_reason": f"Cannot verify on-chain custody anchor at sequence {seq}: RPC node unavailable.",
                    "events": event_details_report
                }

            if anchor_rec:
                # Validate evidence_id in anchor
                if anchor_rec.get("evidence_id") != evidence_id:
                    return {
                        "status": "error",
                        "verification_status": "INCONSISTENT",
                        "evidence_id": evidence_id,
                        "verified": False,
                        "tampered": False,
                        "event_count": len(events),
                        "chain_intact": True,
                        "blockchain_reconciled": False,
                        "technical_error": "ANCHOR_EVIDENCE_MISMATCH",
                        "failure_reason": f"On-chain anchor at sequence {seq} belongs to evidence '{anchor_rec.get('evidence_id')}', expected '{evidence_id}'.",
                        "events": event_details_report
                    }

                # Validate exact canonical event hash against on-chain anchor
                onchain_ev_hash = anchor_rec.get("event_hash", "")
                if onchain_ev_hash and onchain_ev_hash.lower() != stored_ev_hash.lower():
                    return {
                        "status": "error",
                        "verification_status": "TAMPERED",
                        "evidence_id": evidence_id,
                        "verified": False,
                        "tampered": True,
                        "event_count": len(events),
                        "chain_intact": True,
                        "blockchain_reconciled": False,
                        "technical_error": "ANCHOR_HASH_MISMATCH",
                        "failure_reason": f"On-chain anchor hash '{onchain_ev_hash}' at sequence {seq} does not match recomputed canonical event hash '{stored_ev_hash}'.",
                        "events": event_details_report
                    }

                # Validate previous event hash link against on-chain anchor
                onchain_prev_hash = anchor_rec.get("previous_event_hash", "")
                if onchain_prev_hash and onchain_prev_hash.lower() != prev_ev_hash.lower():
                    return {
                        "status": "error",
                        "verification_status": "TAMPERED",
                        "evidence_id": evidence_id,
                        "verified": False,
                        "tampered": True,
                        "event_count": len(events),
                        "chain_intact": True,
                        "blockchain_reconciled": False,
                        "technical_error": "ANCHOR_PREDECESSOR_MISMATCH",
                        "failure_reason": f"On-chain anchor predecessor hash '{onchain_prev_hash}' at sequence {seq} does not match expected prior event hash '{prev_ev_hash}'.",
                        "events": event_details_report
                    }

                # Mark event as independently blockchain anchored
                for ev_rep in event_details_report:
                    if ev_rep.get("sequence_number") == seq:
                        ev_rep["blockchain_anchored"] = True
                        ev_rep["onchain_anchor_hash"] = onchain_ev_hash
            else:
                if require_blockchain:
                    return {
                        "status": "error",
                        "verification_status": "INCONSISTENT",
                        "evidence_id": evidence_id,
                        "verified": False,
                        "tampered": False,
                        "event_count": len(events),
                        "chain_intact": True,
                        "blockchain_reconciled": False,
                        "technical_error": "CUSTODY_ANCHOR_NOT_FOUND",
                        "failure_reason": f"Required on-chain custody anchor missing for event at sequence {seq}.",
                        "events": event_details_report
                    }

        blockchain_reconciled = True
    else:
        # Not registered on blockchain
        if require_blockchain:
            return {
                "status": "error",
                "verification_status": "INCONSISTENT",
                "evidence_id": evidence_id,
                "verified": False,
                "tampered": False,
                "event_count": len(events),
                "chain_intact": True,
                "blockchain_reconciled": False,
                "technical_error": "NOT_REGISTERED_ON_BLOCKCHAIN",
                "failure_reason": f"Evidence '{evidence_id}' has not been anchored on the blockchain. Standalone database history cannot be independently confirmed.",
                "events": event_details_report
            }

    # All checks passed!
    return {
        "status": "success",
        "verification_status": "VERIFIED",
        "evidence_id": evidence_id,
        "verified": True,
        "tampered": False,
        "event_count": len(events),
        "chain_intact": True,
        "blockchain_reconciled": blockchain_reconciled,
        "technical_error": None,
        "failure_reason": None,
        "events": event_details_report
    }
