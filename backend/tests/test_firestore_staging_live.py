"""
ChainVault Phase 4F — Live Cloud Firestore Staging Integration Test Runner
==========================================================================
Validates ChainVault's Cloud Firestore persistence adapter against the live
Google Cloud Firestore staging database ('chainvault-staging', '(default)').

STRICT SAFETY CONTROLS & GUARDRAILS:
1. OPT-IN MANDATORY: Skips all live cloud tests unless explicitly enabled via
   CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS=true.
2. PRE-WRITE VALIDATION: Asserts target project is strictly 'chainvault-staging',
   database is '(default)', emulator mode is disabled, and DATABASE_BACKEND remains 'mongodb'.
3. DETERMINISTIC SYNTHETIC NAMESPACE: Generates IDs with 'STG-TEST-<run_id>-<entity>'.
   Never targets or queries existing application records.
4. OWNERSHIP-BASED CLEANUP: Tracks exact document IDs created during the test run
   and validates that each document still carries this run's unique '_test_run_marker'
   before deleting. Never performs broad prefix sweeps.
5. ISOLATED TEMPORARY STORAGE: Synthetic evidence files and reports are created in
   a dedicated TemporaryDirectory and unlinked immediately during teardown.
6. NO CREDENTIAL LEAKS: Sanitizes all diagnostics to prevent secret exposure.
"""

import os
import sys
import uuid
import time
import shutil
import asyncio
import logging
import tempfile
import datetime
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pytest
from google.api_core.exceptions import AlreadyExists, NotFound

try:
    from google.cloud.firestore_v1.async_transaction import async_transactional
except ImportError:
    async_transactional = None

# Set up logger
logger = logging.getLogger("chainvault.staging_live_tests")

# Configuration constants
REQUIRED_PROJECT_ID = "chainvault-staging"
REQUIRED_DATABASE_ID = "(default)"
OPT_IN_ENV_VAR = "CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS"


class StagingSafetyViolation(Exception):
    """Raised when any staging safety guardrail is breached."""
    pass


def is_live_testing_opted_in() -> bool:
    """Check if the operator has explicitly enabled live Cloud Firestore tests."""
    val = os.getenv(OPT_IN_ENV_VAR, "").strip().lower()
    return val in ("true", "1", "yes")


def validate_staging_target_safety(
    project_id: str,
    database_id: str,
    emulator_host: Optional[str] = None,
    active_backend: Optional[str] = None
) -> None:
    """
    Enforce strict pre-flight guardrails before any live Cloud Firestore connection.
    Fails closed if any target parameter differs from expected staging configuration.
    """
    if not is_live_testing_opted_in():
        raise StagingSafetyViolation(
            f"SAFETY GUARD: Live Cloud Firestore tests require explicit opt-in via {OPT_IN_ENV_VAR}=true."
        )

    if project_id != REQUIRED_PROJECT_ID:
        raise StagingSafetyViolation(
            f"SAFETY GUARD: Target project '{project_id}' does not match required staging project '{REQUIRED_PROJECT_ID}'."
        )

    if database_id != REQUIRED_DATABASE_ID:
        raise StagingSafetyViolation(
            f"SAFETY GUARD: Target database '{database_id}' does not match required database '{REQUIRED_DATABASE_ID}'."
        )

    if emulator_host:
        raise StagingSafetyViolation(
            f"SAFETY GUARD: FIRESTORE_EMULATOR_HOST is set to '{emulator_host}'. "
            "Staging live tests must target Cloud Firestore via ADC, not the local emulator."
        )

    backend = (active_backend or os.getenv("DATABASE_BACKEND", "mongodb")).lower().strip()
    if backend != "mongodb":
        raise StagingSafetyViolation(
            f"SAFETY GUARD: Application DATABASE_BACKEND is '{backend}'. "
            "It must remain 'mongodb' to preserve system baseline."
        )


def sanitize_diagnostic_output(data: Any) -> Any:
    """Sanitize diagnostic dictionaries by redacting secrets, private keys, or tokens."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(term in k_lower for term in ("secret", "token", "password", "key", "credential", "auth")):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_diagnostic_output(v)
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(data, list):
        return [sanitize_diagnostic_output(item) for item in data]
    return data


# Dedicated module-level event loop preserving gRPC channel lifecycle
_MODULE_EVENT_LOOP: Optional[asyncio.AbstractEventLoop] = None


def get_staging_event_loop() -> asyncio.AbstractEventLoop:
    """
    Return the persistent, dedicated asyncio event loop for the staging live test suite.
    Ensures that the gRPC async channel created during client.connect() stays bound
    to the exact same active event loop across all live tests, fixtures, and cleanup operations.
    """
    global _MODULE_EVENT_LOOP
    if _MODULE_EVENT_LOOP is None or _MODULE_EVENT_LOOP.is_closed():
        _MODULE_EVENT_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_MODULE_EVENT_LOOP)
    return _MODULE_EVENT_LOOP


def run_async(coro):
    """
    Run an async coroutine synchronously using the persistent staging module event loop.
    Avoids closing and recreating event loops, preventing gRPC channel invalidation.
    """
    loop = get_staging_event_loop()
    return loop.run_until_complete(coro)


class StagingTestRunTracker:
    """
    Tracks documents and files created during a single test run to enforce strictly scoped,
    ownership-verified cleanup. Prevents blanket or prefix-based sweeping.
    """
    def __init__(self, run_id: Optional[str] = None):
        # 128-bit UUID4 hex string guarantees cryptographic collision resistance
        self.run_id = run_id or uuid.uuid4().hex
        self.run_marker = f"STG-RUN-{self.run_id}"
        self._created_docs: List[Tuple[str, str]] = []  # List of (collection_name, doc_id)
        self._created_files: List[Path] = []
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None

    @property
    def temp_dir_path(self) -> Path:
        """Isolated temporary directory strictly for this test run's synthetic files."""
        if self._temp_dir is None:
            self._temp_dir = tempfile.TemporaryDirectory(prefix=f"chainvault_stg_{self.run_id}_")
        return Path(self._temp_dir.name)

    def generate_doc_id(self, entity_prefix: str) -> str:
        """Generate deterministic, run-isolated identifier."""
        return f"STG-TEST-{self.run_id}-{entity_prefix}"

    def record_document_creation(self, collection_name: str, doc_id: str) -> None:
        """Register a document created by this test run for ownership tracking."""
        self._created_docs.append((collection_name, doc_id))

    def record_file_creation(self, file_path: Union[str, Path]) -> None:
        """Register a synthetic file created during the test run."""
        self._created_files.append(Path(file_path))

    def prepare_test_payload(self, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Inject immutable run marker and test ownership metadata into document payload."""
        payload = dict(data)
        payload["_test_run_marker"] = self.run_marker
        payload["_test_run_id"] = self.run_id
        payload["_test_created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return payload

    async def cleanup_owned_documents(self, client: Any) -> Dict[str, int]:
        """
        Deletes ONLY documents recorded by this tracker, and ONLY if the document
        still contains the matching _test_run_marker.

        Attempts atomic transactional deletion via Cloud Firestore AsyncClient transaction
        if client.firestore_client is available. Falls back to two-step check-then-delete
        if transactions are unsupported (e.g. local mock clients in unit tests).
        """
        stats = {"inspected": 0, "deleted": 0, "skipped_unowned": 0, "not_found": 0}

        fs_client = getattr(client, "firestore_client", None)
        can_use_transactions = (
            fs_client is not None
            and hasattr(fs_client, "transaction")
            and async_transactional is not None
        )

        # Process in reverse order of creation
        for col_name, doc_id in reversed(self._created_docs):
            stats["inspected"] += 1

            if can_use_transactions:
                try:
                    doc_ref = fs_client.collection(col_name).document(str(doc_id))
                    txn = fs_client.transaction()

                    @async_transactional
                    async def _txn_delete(transaction):
                        snapshot = await doc_ref.get(transaction=transaction)
                        if not snapshot.exists:
                            return "not_found"
                        data = snapshot.to_dict() or {}
                        if data.get("_test_run_marker") == self.run_marker:
                            transaction.delete(doc_ref)
                            return "deleted"
                        else:
                            return "skipped_unowned"

                    outcome = await _txn_delete(txn)
                    if outcome == "deleted":
                        stats["deleted"] += 1
                        continue
                    elif outcome == "skipped_unowned":
                        stats["skipped_unowned"] += 1
                        logger.warning(
                            f"SAFETY ALERT: Refused to delete {col_name}/{doc_id}; "
                            f"marker mismatch in atomic transaction"
                        )
                        continue
                    elif outcome == "not_found":
                        stats["not_found"] += 1
                        continue
                except Exception as e:
                    logger.debug(f"Transactional cleanup failed for {col_name}/{doc_id}, falling back: {e}")

            # Fallback: two-step check-then-delete via collection adapter
            col_adapter = client[col_name]
            pk_field = getattr(col_adapter, "primary_key", "_id")
            doc = await col_adapter.find_one({pk_field: doc_id})
            if not doc:
                stats["not_found"] += 1
                continue

            # POSITIVE OWNERSHIP VALIDATION
            if doc.get("_test_run_marker") == self.run_marker:
                await col_adapter.delete_one({pk_field: doc_id})
                stats["deleted"] += 1
            else:
                stats["skipped_unowned"] += 1
                logger.warning(
                    f"SAFETY ALERT: Refused to delete {col_name}/{doc_id}; "
                    f"marker mismatch (expected {self.run_marker}, found {doc.get('_test_run_marker')})"
                )

        self._created_docs.clear()
        return stats

    def cleanup_files(self) -> int:
        """Safely delete all temporary synthetic files created during the test run."""
        count = 0
        for f in self._created_files:
            if f.exists() and f.is_file():
                try:
                    f.unlink()
                    count += 1
                except OSError:
                    pass
        if self._temp_dir:
            try:
                self._temp_dir.cleanup()
            except OSError:
                pass
            self._temp_dir = None
        self._created_files.clear()
        return count


# =============================================================================
# MODULE-LEVEL OPT-IN SKIP
# =============================================================================
# Unless CHAINVAULT_RUN_LIVE_FIRESTORE_TESTS=true is explicitly provided,
# all tests in this module skip automatically with zero network calls to the cloud.

pytestmark = pytest.mark.skipif(
    not is_live_testing_opted_in(),
    reason=f"Live Cloud Firestore integration tests are disabled by default. Set {OPT_IN_ENV_VAR}=true to enable."
)


# =============================================================================
# PYTEST FIXTURES (ACTIVE ONLY WHEN OPTED IN)
# =============================================================================

@pytest.fixture(scope="module")
def staging_client():
    """Module-scoped FirestoreClient connected to chainvault-staging via ADC."""
    from app.database.firestore import FirestoreClient

    client = FirestoreClient()
    validate_staging_target_safety(
        project_id=client.project_id,
        database_id=client.database_id,
        emulator_host=client.emulator_host,
        active_backend=os.getenv("DATABASE_BACKEND", "mongodb")
    )

    run_async(client.connect())
    assert client.is_connected(), "Failed to connect to Cloud Firestore via ADC"
    try:
        yield client
    finally:
        # 1. Close Firestore async client on the persistent module loop
        try:
            run_async(client.close())
        except Exception as e:
            logger.warning(f"Error closing staging Firestore client: {e}")

        # 2. Cleanly teardown any lingering asyncio tasks and close module loop
        global _MODULE_EVENT_LOOP
        if _MODULE_EVENT_LOOP and not _MODULE_EVENT_LOOP.is_closed():
            try:
                pending = [t for t in asyncio.all_tasks(_MODULE_EVENT_LOOP) if not t.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    _MODULE_EVENT_LOOP.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception as e:
                logger.debug(f"Error cleaning pending loop tasks: {e}")
            finally:
                _MODULE_EVENT_LOOP.close()
                _MODULE_EVENT_LOOP = None


@pytest.fixture
def tracker(staging_client):
    """Function-scoped tracker managing deterministic document lifecycle and cleanup."""
    run_tracker = StagingTestRunTracker()
    try:
        yield run_tracker
    finally:
        stats = run_async(run_tracker.cleanup_owned_documents(staging_client))
        files_cleaned = run_tracker.cleanup_files()
        leftovers = stats.get("skipped_unowned", 0)
        if leftovers > 0:
            logger.warning(f"LEFTOVER ALERT: {leftovers} document(s) could not be cleaned up: {stats}")
        logger.info(f"Staging tracker cleanup finished: docs={stats}, files={files_cleaned}")



# =============================================================================
# SUITE 1: READ-ONLY CLOUD CONNECTIVITY & PROBE (ZERO WRITES)
# =============================================================================

def test_suite1_cloud_handshake_and_ping(staging_client):
    """Suite 1.1: Verify live ping to Cloud Firestore database '(default)'."""
    async def _test():
        is_live = await staging_client.ping()
        assert is_live is True, "Cloud Firestore ping failed"
    run_async(_test())


def test_suite1_negative_document_lookup(staging_client):
    """Suite 1.2: Verify querying a non-existent document safely returns None without exception."""
    async def _test():
        result = await staging_client.cases.find_one({"case_id": "NON_EXISTENT_CASE_99999"})
        assert result is None
    run_async(_test())


def test_suite1_empty_collection_streaming(staging_client):
    """Suite 1.3: Verify cursor iteration on non-matching query returns empty list cleanly."""
    async def _test():
        cursor = staging_client.evidence.find({"evidence_id": "NON_EXISTENT_EV_99999"})
        docs = await cursor.to_list(10)
        assert docs == []
    run_async(_test())


# =============================================================================
# SUITE 2: DETERMINISTIC ID MAPPING & DOCUMENT CRUD (ISOLATED WRITES)
# =============================================================================

def test_suite2_case_document_deterministic_id_crud(staging_client, tracker):
    """Suite 2.1: Verify deterministic document keying and CRUD on live Cloud Firestore."""
    async def _test():
        case_id = tracker.generate_doc_id("CS-01")
        raw_case = {
            "case_id": case_id,
            "title": "Staging Verification Case",
            "status": "OPEN",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "is_deleted": False
        }
        payload = tracker.prepare_test_payload(case_id, raw_case)

        # 1. Pre-register for tracking before write to handle mid-flight network/timeout faults
        tracker.record_document_creation("cases", case_id)
        insert_res = await staging_client.cases.insert_one(payload)
        assert insert_res.inserted_id == case_id

        # 2. Read back
        retrieved = await staging_client.cases.find_one({"case_id": case_id})
        assert retrieved is not None
        assert retrieved["case_id"] == case_id
        assert retrieved["title"] == "Staging Verification Case"
        assert retrieved["_test_run_marker"] == tracker.run_marker
    run_async(_test())


def test_suite2_duplicate_id_atomic_rejection(staging_client, tracker):
    """Suite 2.2: Verify insert_one refuses to overwrite an existing record with create()."""
    async def _test():
        case_id = tracker.generate_doc_id("CS-DUP")
        payload = tracker.prepare_test_payload(case_id, {
            "case_id": case_id,
            "title": "Initial Document",
            "status": "OPEN"
        })

        tracker.record_document_creation("cases", case_id)
        await staging_client.cases.insert_one(payload)

        # Second insert with identical ID must raise AlreadyExists
        with pytest.raises(AlreadyExists):
            await staging_client.cases.insert_one(payload)
    run_async(_test())


def test_suite2_atomic_update_and_increment(staging_client, tracker):
    """Suite 2.3: Verify update_one handles $set and $inc atomically on Cloud Firestore."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-UPDATE")
        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "status": "STORED",
            "custody_version": 1
        })

        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        # Update with $set and $inc
        update_res = await staging_client.evidence.update_one(
            {"evidence_id": ev_id},
            {
                "$set": {"status": "TRANSFERRED"},
                "$inc": {"custody_version": 1}
            }
        )
        assert update_res.modified_count == 1

        updated_doc = await staging_client.evidence.find_one({"evidence_id": ev_id})
        assert updated_doc["status"] == "TRANSFERRED"
        assert updated_doc["custody_version"] == 2
    run_async(_test())


def test_suite2_primitive_type_serialization(staging_client, tracker):
    """Suite 2.4: Verify stripping of internal BSON keys and preservation of JSON primitives."""
    async def _test():
        user_id = tracker.generate_doc_id("USR-01")
        payload = tracker.prepare_test_payload(user_id, {
            "username": user_id,
            "role": "OFFICER",
            "is_active": True,
            "login_count": 0
        })

        tracker.record_document_creation("users", user_id)
        await staging_client.users.insert_one(payload)

        doc = await staging_client.users.find_one({"username": user_id})
        assert "_id" not in doc
        assert doc["is_active"] is True
        assert doc["login_count"] == 0
    run_async(_test())


# =============================================================================
# SUITE 3: AUDIT TRAIL INVARIANCE & COMPOSITE INDEX EXECUTION
# =============================================================================

def test_suite3_canonical_timestamp_rfc3339_string_preservation(staging_client, tracker):
    """Suite 3.1: Verify timestamps remain exact RFC 3339 strings and do not convert to protobuf Timestamps."""
    async def _test():
        evt_id = tracker.generate_doc_id("EVT-TIME-01")
        canonical_ts = "2026-10-24T12:00:00.000000Z"

        payload = tracker.prepare_test_payload(evt_id, {
            "event_id": evt_id,
            "evidence_id": tracker.generate_doc_id("EV-REF-01"),
            "timestamp": canonical_ts,
            "sequence_number": 1
        })

        tracker.record_document_creation("audit_logs", evt_id)
        await staging_client.audit_logs.insert_one(payload)

        doc = await staging_client.audit_logs.find_one({"event_id": evt_id})
        assert isinstance(doc["timestamp"], str)
        assert doc["timestamp"] == canonical_ts
    run_async(_test())


def test_suite3_sequential_merkle_audit_chain_verification(staging_client, tracker):
    """Suite 3.2: Verify sequential Merkle chain calculation and roundtrip persistence."""
    async def _test():
        from app.services.audit_trail import calculate_canonical_event_hash

        evidence_id = tracker.generate_doc_id("EV-CHAIN")
        prev_hash = "0" * 64
        event_ids = []

        for seq in range(1, 4):
            evt_id = tracker.generate_doc_id(f"EVT-SEQ-{seq}")
            event_data = {
                "event_id": evt_id,
                "evidence_id": evidence_id,
                "action": f"STEP_{seq}",
                "sequence_number": seq,
                "previous_event_hash": prev_hash,
                "timestamp": f"2026-10-24T12:0{seq}:00.000000Z"
            }
            calculated_hash = calculate_canonical_event_hash(event_data)
            event_data["event_hash"] = calculated_hash

            payload = tracker.prepare_test_payload(evt_id, event_data)
            tracker.record_document_creation("audit_logs", evt_id)
            await staging_client.audit_logs.insert_one(payload)
            event_ids.append(evt_id)
            prev_hash = calculated_hash

        # Verify all 3 in sequence
        for idx, e_id in enumerate(event_ids, start=1):
            d = await staging_client.audit_logs.find_one({"event_id": e_id})
            assert d["sequence_number"] == idx
            recalculated = calculate_canonical_event_hash({k: v for k, v in d.items() if not k.startswith("_test")})
            assert recalculated == d["event_hash"]
    run_async(_test())


def test_suite3_composite_index_query_execution(staging_client, tracker):
    """
    Suite 3.3: Exercise the composite index (evidence_id ASC, sequence_number ASC)
    against live Cloud Firestore. If index is missing, Cloud Firestore throws FAILED_PRECONDITION.
    """
    async def _test():
        ev_id = tracker.generate_doc_id("EV-INDEX-TEST")

        for seq in [3, 1, 2]:
            evt_id = tracker.generate_doc_id(f"EVT-IDX-{seq}")
            payload = tracker.prepare_test_payload(evt_id, {
                "event_id": evt_id,
                "evidence_id": ev_id,
                "sequence_number": seq,
                "timestamp": f"2026-10-24T12:0{seq}:00.000000Z"
            })
            tracker.record_document_creation("audit_logs", evt_id)
            await staging_client.audit_logs.insert_one(payload)

        # Execute composite query requiring index
        cursor = staging_client.audit_logs.find({"evidence_id": ev_id}).sort("sequence_number", 1)
        results = await cursor.to_list(10)

        assert len(results) == 3
        # Check that sorting order ASC is respected
        assert [r["sequence_number"] for r in results] == [1, 2, 3]
    run_async(_test())


# =============================================================================
# SUITE 4: DISTRIBUTED CONCURRENCY, CUSTODY LEASE LOCKING & FENCING
# =============================================================================

def test_suite4_atomic_lease_lock_acquisition(staging_client, tracker):
    """Suite 4.1: Acquire distributed lease lock on evidence record via Firestore transaction."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-LOCK-01")
        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "custodian": "officer_initial",
            "custody_version": 1,
            "status": "STORED"
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        acquired, token, reason, ver = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="officer_alice",
            lease_seconds=30.0
        )
        assert acquired is True
        assert token is not None
        assert reason is None
        assert ver == 1

        # Verify lock stored on document
        doc = await staging_client.evidence.find_one({"evidence_id": ev_id})
        assert doc["transfer_lock"]["status"] == "LOCKED"
        assert doc["transfer_lock"]["actor"] == "officer_alice"
    run_async(_test())


def test_suite4_concurrent_lease_collision_rejection(staging_client, tracker):
    """Suite 4.2: Assert second concurrent worker is rejected with 'LOCKED'."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-COLLIDE-01")
        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "custodian": "officer_initial",
            "custody_version": 1
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        # Worker A acquires
        acq_a, tok_a, _, _ = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_a",
            lease_seconds=30.0
        )
        assert acq_a is True

        # Worker B attempts to acquire on same document
        acq_b, tok_b, reason_b, _ = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_b",
            wait_timeout=0.1
        )
        assert acq_b is False
        assert tok_b is None
        assert reason_b == "LOCKED"
    run_async(_test())


def test_suite4_lease_renewal_verification(staging_client, tracker):
    """Suite 4.3: Renew custody transfer lock extending expiration timestamp."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-RENEW-01")
        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "custodian": "officer_initial",
            "custody_version": 1
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        acq, token, _, _ = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_a",
            lease_seconds=10.0
        )
        assert acq is True

        renewed = await staging_client.renew_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=token,
            additional_seconds=60.0
        )
        assert renewed is True
    run_async(_test())


def test_suite4_fencing_version_increment_on_release(staging_client, tracker):
    """Suite 4.4: Release lock and increment fencing version atomically."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-FENCE-01")
        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "custodian": "custodian_a",
            "custody_version": 1
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        acq, token, _, ver = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_a"
        )
        assert acq is True

        released = await staging_client.release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=token,
            new_custodian="custodian_b",
            expected_version=ver
        )
        assert released is True

        updated_doc = await staging_client.evidence.find_one({"evidence_id": ev_id})
        assert updated_doc["custodian"] == "custodian_b"
        assert updated_doc["custody_version"] == 2
        assert updated_doc["transfer_lock"]["status"] == "UNLOCKED"
    run_async(_test())


def test_suite4_stale_fencing_version_rejection(staging_client, tracker):
    """Suite 4.5: Releasing with stale fencing version fails closed."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-STALE-01")
        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "custodian": "custodian_a",
            "custody_version": 2
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        acq, token, _, ver = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="worker_a"
        )
        assert acq is True

        # Attempt release with wrong expected version (1 instead of 2)
        released = await staging_client.release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=token,
            new_custodian="custodian_b",
            expected_version=1
        )
        assert released is False

        # Document remains at version 2, custodian unchanged
        doc = await staging_client.evidence.find_one({"evidence_id": ev_id})
        assert doc["custody_version"] == 2
        assert doc["custodian"] == "custodian_a"
    run_async(_test())


# =============================================================================
# SUITE 5: DECOUPLED BINARY STORAGE & FORENSIC REPORTS
# =============================================================================

def test_suite5_storage_decoupling_evidence_binary_on_disk(staging_client, tracker):
    """Suite 5.1: Assert file bytes remain in temp directory and are never stored in Cloud Firestore."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-DECOUPLED-01")
        raw_content = b"CHAINVAULT_SYNTHETIC_STAGING_PAYLOAD_TEST_BYTES"
        sha256_hash = hashlib.sha256(raw_content).hexdigest().lower()

        # Write to tracker's isolated temporary directory
        temp_file = tracker.temp_dir_path / f"stg_test_{ev_id}.bin"
        temp_file.write_bytes(raw_content)
        tracker.record_file_creation(temp_file)

        payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "file_hash": sha256_hash,
            "file_path": str(temp_file),
            "file_size": len(raw_content),
            "status": "STORED"
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(payload)

        # Read back from Cloud Firestore
        stored_doc = await staging_client.evidence.find_one({"evidence_id": ev_id})
        assert stored_doc["file_hash"] == sha256_hash
        assert stored_doc["file_path"] == str(temp_file)
        assert "content" not in stored_doc
        assert "binary" not in stored_doc

        # Verify physical file on disk matches hash
        disk_hash = hashlib.sha256(Path(stored_doc["file_path"]).read_bytes()).hexdigest().lower()
        assert disk_hash == sha256_hash
    run_async(_test())


def test_suite5_forensic_report_metadata_and_verification(staging_client, tracker):
    """Suite 5.2: Create report metadata in Firestore and verify against PDF on disk."""
    async def _test():
        rep_id = tracker.generate_doc_id("REP-01")
        pdf_bytes = b"%PDF-1.4 ChainVault Staging Synthetic Test Report Content"
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest().lower()

        temp_pdf = tracker.temp_dir_path / f"stg_test_{rep_id}.pdf"
        temp_pdf.write_bytes(pdf_bytes)
        tracker.record_file_creation(temp_pdf)

        payload = tracker.prepare_test_payload(rep_id, {
            "report_id": rep_id,
            "case_id": tracker.generate_doc_id("CS-REP-01"),
            "report_hash": pdf_hash,
            "file_path": str(temp_pdf),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        tracker.record_document_creation("reports", rep_id)
        await staging_client.reports.insert_one(payload)

        doc = await staging_client.reports.find_one({"report_id": rep_id})
        assert doc is not None
        assert doc["report_hash"] == pdf_hash

        # Re-verify checksum from disk
        assert hashlib.sha256(Path(doc["file_path"]).read_bytes()).hexdigest().lower() == doc["report_hash"]
    run_async(_test())


def test_suite5_composite_index_report_case_chronology(staging_client, tracker):
    """Suite 5.3: Exercise composite index (case_id ASC, generated_at DESC)."""
    async def _test():
        case_id = tracker.generate_doc_id("CS-CHRONO")

        for i in range(1, 4):
            rep_id = tracker.generate_doc_id(f"REP-CHRONO-{i}")
            payload = tracker.prepare_test_payload(rep_id, {
                "report_id": rep_id,
                "case_id": case_id,
                "generated_at": f"2026-10-24T12:0{i}:00.000000Z"
            })
            tracker.record_document_creation("reports", rep_id)
            await staging_client.reports.insert_one(payload)

        # Composite query
        cursor = staging_client.reports.find({"case_id": case_id}).sort("generated_at", -1)
        reps = await cursor.to_list(10)
        assert len(reps) == 3
        # Check descending chronology
        assert reps[0]["generated_at"] > reps[1]["generated_at"] > reps[2]["generated_at"]
    run_async(_test())


# =============================================================================
# SUITE 6: END-TO-END WORKFLOW & DIAGNOSTICS
# =============================================================================

def test_suite6_system_diagnostics_integration(staging_client):
    """Suite 6.1: Run get_system_diagnostics and verify non-sensitive health reporting."""
    async def _test():
        from app.services.recovery import get_system_diagnostics
        diag = await get_system_diagnostics()
        sanitized = sanitize_diagnostic_output(diag)

        assert "persistence_mode" in sanitized
        assert "ready_for_verification" in sanitized
        # Assert no secrets
        assert "secret" not in str(sanitized).lower()
        assert "token" not in str(sanitized).lower()
    run_async(_test())


def test_suite6_full_custody_transfer_lifecycle(staging_client, tracker):
    """Suite 6.2: End-to-end custody transfer registration, locking, and resolution."""
    async def _test():
        ev_id = tracker.generate_doc_id("EV-E2E-01")
        tx_id = tracker.generate_doc_id("TX-E2E-01")
        idem_key = tracker.generate_doc_id("IDEM-E2E-01")

        # 1. Evidence document
        ev_payload = tracker.prepare_test_payload(ev_id, {
            "evidence_id": ev_id,
            "custodian": "officer_source",
            "custody_version": 1,
            "status": "STORED"
        })
        tracker.record_document_creation("evidence", ev_id)
        await staging_client.evidence.insert_one(ev_payload)

        # 2. Acquire lock
        acq, lock_tok, _, ver = await staging_client.acquire_custody_transfer_lock(
            evidence_id=ev_id,
            actor="officer_source"
        )
        assert acq is True

        # 3. Create durable transaction record
        tx_payload = tracker.prepare_test_payload(tx_id, {
            "transaction_id": tx_id,
            "evidence_id": ev_id,
            "idempotency_key": idem_key,
            "status": "PREPARED",
            "new_custodian": "officer_target",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        tracker.record_document_creation("custody_transactions", tx_id)
        await staging_client.custody_transactions.insert_one(tx_payload)

        # 4. Release lock with CAS version update
        released = await staging_client.release_custody_transfer_lock(
            evidence_id=ev_id,
            lock_token=lock_tok,
            new_custodian="officer_target",
            expected_version=ver
        )
        assert released is True

        # 5. Update transaction to CONFIRMED
        await staging_client.custody_transactions.update_one(
            {"transaction_id": tx_id},
            {"$set": {"status": "CONFIRMED"}}
        )

        # Verification
        final_ev = await staging_client.evidence.find_one({"evidence_id": ev_id})
        assert final_ev["custodian"] == "officer_target"
        assert final_ev["custody_version"] == 2

        final_tx = await staging_client.custody_transactions.find_one({"transaction_id": tx_id})
        assert final_tx["status"] == "CONFIRMED"
    run_async(_test())
