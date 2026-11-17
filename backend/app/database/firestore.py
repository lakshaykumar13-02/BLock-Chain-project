import os
import time
import inspect
import asyncio
import logging
from typing import Any, Optional, Union, Dict, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

from .base import BaseDatabaseClient

try:
    from google.cloud import firestore
    from google.cloud.firestore import AsyncClient
    from google.cloud.firestore_v1.async_transaction import async_transactional
    from google.cloud.firestore_v1.base_query import FieldFilter
    from google.api_core.exceptions import NotFound, AlreadyExists, GoogleAPICallError
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    AsyncClient = None
    async_transactional = None
    FieldFilter = None
    NotFound = Exception
    AlreadyExists = Exception
    GoogleAPICallError = Exception


class FirestoreInsertResult:
    def __init__(self, inserted_id: str):
        self.inserted_id = inserted_id


class FirestoreUpdateResult:
    def __init__(self, matched_count: int, modified_count: int, upserted_id: Optional[str] = None):
        self.matched_count = matched_count
        self.modified_count = modified_count
        self.upserted_id = upserted_id


class FirestoreDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class FirestoreCursor:
    """Async cursor that mimics Motor's cursor interface (to_list and async iteration)."""
    def __init__(self, query_or_docs, projection: Optional[dict] = None):
        self._source = query_or_docs
        self._projection = projection
        self._docs = None
        self._sort_field = None
        self._sort_direction = None
        self._skip_count = 0
        self._limit_count = None

    def sort(self, field: str, direction: int = 1):
        self._sort_field = field
        self._sort_direction = direction
        return self

    def skip(self, count: int):
        self._skip_count = max(0, int(count or 0))
        return self

    def limit(self, count: int):
        self._limit_count = max(0, int(count or 0)) if count is not None else None
        return self

    async def _fetch(self):
        if self._docs is not None:
            return self._docs

        results = []
        if isinstance(self._source, list):
            results = [dict(d) for d in self._source]
        elif hasattr(self._source, "stream"):
            async for doc in self._source.stream():
                d = doc.to_dict() or {}
                results.append(d)
        elif hasattr(self._source, "get"):
            snapshots = await self._source.get()
            for doc in snapshots:
                d = doc.to_dict() or {}
                results.append(d)
        else:
            results = []

        if self._sort_field:
            reverse = bool(self._sort_direction == -1)
            results.sort(key=lambda x: x.get(self._sort_field) or "", reverse=reverse)

        self._docs = results
        return self._docs

    async def to_list(self, length: Optional[int] = 1000) -> List[dict]:
        docs = await self._fetch()
        start = self._skip_count or 0
        effective_limit = self._limit_count if self._limit_count is not None else length
        if effective_limit is not None:
            return docs[start:start + effective_limit]
        return docs[start:]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._docs is None:
            await self._fetch()
            self._idx = self._skip_count or 0
        max_idx = len(self._docs)
        if self._limit_count is not None:
            max_idx = min(max_idx, (self._skip_count or 0) + self._limit_count)
        if self._idx < max_idx:
            item = self._docs[self._idx]
            self._idx += 1
            return item
        raise StopAsyncIteration


class FirestoreCollectionAdapter:
    """
    Adapter bridging Motor collection syntax (find, find_one, update_one, insert_one, delete_one)
    to Cloud Firestore collections with deterministic document IDs.
    """
    PRIMARY_KEYS = {
        "cases": "case_id",
        "evidence": "evidence_id",
        "audit_logs": "event_id",
        "custody_transactions": "transaction_id",
        "idempotency_records": "idempotency_key",
        "blockchain_checkpoints": "checkpoint_id",
        "reports": "report_id",
        "users": "username"
    }

    def __init__(self, client: "FirestoreClient", collection_name: str):
        self.client = client
        self.collection_name = collection_name
        self.primary_key = self.PRIMARY_KEYS.get(collection_name, "_id")

    def _get_doc_id(self, doc_or_filter: dict) -> Optional[str]:
        if not doc_or_filter or not isinstance(doc_or_filter, dict):
            return None
        if self.primary_key in doc_or_filter:
            val = doc_or_filter[self.primary_key]
            if isinstance(val, str) and val.strip():
                return val.strip()
        if "_id" in doc_or_filter:
            val = doc_or_filter["_id"]
            if isinstance(val, str) and val.strip():
                return val.strip()
        # Fallbacks for secondary identifiers
        if self.collection_name == "blockchain_checkpoints" and "evidence_id" in doc_or_filter:
            return f"CHK-{doc_or_filter['evidence_id']}"
        return None

    def _clean_doc_for_storage(self, doc: dict) -> dict:
        """Ensure dictionary stores serializable primitives, stripping internal keys."""
        cleaned = {}
        for k, v in doc.items():
            if k == "_id":
                continue
            cleaned[k] = v
        return cleaned

    async def insert_one(self, doc: dict) -> FirestoreInsertResult:
        data = self._clean_doc_for_storage(doc)
        doc_id = self._get_doc_id(doc) or doc.get("event_id") or doc.get("transaction_id") or doc.get("report_id")

        if not self.client.is_connected():
            if self.client.require_persistent_storage:
                raise RuntimeError(f"Firestore persistent storage is required but currently unavailable")
            return FirestoreInsertResult(doc_id or "local_id")

        fs_client = self.client.firestore_client
        col_ref = fs_client.collection(self.collection_name)
        if doc_id:
            doc_ref = col_ref.document(str(doc_id))
            try:
                # Use create() to guarantee uniqueness against existing records
                await doc_ref.create(data)
            except AlreadyExists:
                # If already exists, raise conflict or error as required
                raise
            return FirestoreInsertResult(str(doc_id))
        else:
            doc_ref = col_ref.document()
            await doc_ref.set(data)
            return FirestoreInsertResult(doc_ref.id)

    async def find_one(self, filter_query: Optional[dict] = None, projection: Optional[dict] = None) -> Optional[dict]:
        if not self.client.is_connected():
            if self.client.require_persistent_storage:
                raise RuntimeError("Firestore persistent storage is required but currently unavailable")
            return None

        fs_client = self.client.firestore_client
        col_ref = fs_client.collection(self.collection_name)
        filter_dict = filter_query or {}

        doc_id = self._get_doc_id(filter_dict)
        if doc_id:
            doc_ref = col_ref.document(str(doc_id))
            snapshot = await doc_ref.get()
            if snapshot.exists:
                res = snapshot.to_dict() or {}
                if not projection or projection.get("_id") == 0:
                    res.pop("_id", None)
                return res
            return None

        # Query-based find_one
        query = col_ref
        for field, condition in filter_dict.items():
            if field == "_id":
                continue
            if isinstance(condition, dict):
                if "$in" in condition:
                    query = query.where(filter=FieldFilter(field, "in", condition["$in"]))
                elif "$ne" in condition:
                    query = query.where(filter=FieldFilter(field, "!=", condition["$ne"]))
                elif "$lt" in condition:
                    query = query.where(filter=FieldFilter(field, "<", condition["$lt"]))
                elif "$gt" in condition:
                    query = query.where(filter=FieldFilter(field, ">", condition["$gt"]))
            else:
                query = query.where(filter=FieldFilter(field, "==", condition))

        query = query.limit(1)
        snapshots = await query.get()
        for s in snapshots:
            d = s.to_dict() or {}
            if not projection or projection.get("_id") == 0:
                d.pop("_id", None)
            return d
        return None

    def find(self, filter_query: Optional[dict] = None, projection: Optional[dict] = None) -> FirestoreCursor:
        if not self.client.is_connected():
            if self.client.require_persistent_storage:
                raise RuntimeError("Firestore persistent storage is required but currently unavailable")
            return FirestoreCursor([])

        fs_client = self.client.firestore_client
        query = fs_client.collection(self.collection_name)
        filter_dict = filter_query or {}

        for field, condition in filter_dict.items():
            if field == "_id":
                continue
            if isinstance(condition, dict):
                if "$ne" in condition:
                    query = query.where(filter=FieldFilter(field, "!=", condition["$ne"]))
                elif "$in" in condition:
                    query = query.where(filter=FieldFilter(field, "in", condition["$in"]))
                elif "$lt" in condition:
                    query = query.where(filter=FieldFilter(field, "<", condition["$lt"]))
                elif "$gt" in condition:
                    query = query.where(filter=FieldFilter(field, ">", condition["$gt"]))
            else:
                query = query.where(filter=FieldFilter(field, "==", condition))

        return FirestoreCursor(query, projection)

    async def update_one(self, filter_query: dict, update_doc: dict, upsert: bool = False) -> FirestoreUpdateResult:
        if not self.client.is_connected():
            if self.client.require_persistent_storage:
                raise RuntimeError("Firestore persistent storage is required but currently unavailable")
            return FirestoreUpdateResult(0, 0)

        fs_client = self.client.firestore_client
        col_ref = fs_client.collection(self.collection_name)
        doc_id = self._get_doc_id(filter_query)

        # Parse update document ($set, $inc)
        sets = update_doc.get("$set", {})
        incs = update_doc.get("$inc", {})
        payload = dict(sets)
        for k, v in incs.items():
            payload[k] = firestore.Increment(v)

        if doc_id:
            doc_ref = col_ref.document(str(doc_id))
            if upsert:
                # Merge update
                await doc_ref.set(payload, merge=True)
                return FirestoreUpdateResult(1, 1, str(doc_id))

            # Non-upsert update
            snapshot = await doc_ref.get()
            if not snapshot.exists:
                return FirestoreUpdateResult(0, 0)

            # Check additional filter conditions if present (e.g. custody lock conditions)
            current_data = snapshot.to_dict() or {}
            for k, expected in filter_query.items():
                if k in (self.primary_key, "_id"):
                    continue
                if k == "$or":
                    # Evaluates lease condition
                    now = time.time()
                    satisfied = False
                    for cond in expected:
                        if "transfer_lock" in cond and cond["transfer_lock"].get("$exists") is False:
                            if "transfer_lock" not in current_data or not current_data["transfer_lock"]:
                                satisfied = True
                                break
                        elif "transfer_lock.status" in cond and cond["transfer_lock.status"].get("$ne"):
                            curr_st = current_data.get("transfer_lock", {}).get("status")
                            if curr_st != cond["transfer_lock.status"]["$ne"]:
                                satisfied = True
                                break
                        elif "transfer_lock.expires_at" in cond and cond["transfer_lock.expires_at"].get("$lt"):
                            curr_exp = current_data.get("transfer_lock", {}).get("expires_at", 0)
                            if curr_exp < cond["transfer_lock.expires_at"]["$lt"]:
                                satisfied = True
                                break
                    if not satisfied:
                        return FirestoreUpdateResult(1, 0)
                elif "." in k:
                    # Nested field match (e.g. transfer_lock.lock_token)
                    parts = k.split(".")
                    cur = current_data
                    for p in parts:
                        cur = cur.get(p) if isinstance(cur, dict) else None
                    if cur != expected:
                        return FirestoreUpdateResult(1, 0)
                else:
                    if current_data.get(k) != expected:
                        return FirestoreUpdateResult(1, 0)

            await doc_ref.update(payload)
            return FirestoreUpdateResult(1, 1)

        # Document ID not in filter: query first matching document
        query = col_ref
        for field, condition in filter_query.items():
            if isinstance(condition, dict) and "$in" in condition:
                query = query.where(filter=FieldFilter(field, "in", condition["$in"]))
            else:
                query = query.where(filter=FieldFilter(field, "==", condition))
        snapshots = await query.limit(1).get()
        for s in snapshots:
            await s.reference.update(payload)
            return FirestoreUpdateResult(1, 1)

        if upsert:
            new_doc = col_ref.document()
            await new_doc.set(payload)
            return FirestoreUpdateResult(0, 1, new_doc.id)

        return FirestoreUpdateResult(0, 0)

    async def delete_one(self, filter_query: dict) -> FirestoreDeleteResult:
        if not self.client.is_connected():
            if self.client.require_persistent_storage:
                raise RuntimeError("Firestore persistent storage is required but currently unavailable")
            return FirestoreDeleteResult(0)

        fs_client = self.client.firestore_client
        col_ref = fs_client.collection(self.collection_name)
        doc_id = self._get_doc_id(filter_query)
        if doc_id:
            doc_ref = col_ref.document(str(doc_id))
            await doc_ref.delete()
            return FirestoreDeleteResult(1)

        query = col_ref
        for field, val in filter_query.items():
            query = query.where(filter=FieldFilter(field, "==", val))
        snapshots = await query.limit(1).get()
        for s in snapshots:
            await s.reference.delete()
            return FirestoreDeleteResult(1)
        return FirestoreDeleteResult(0)

    async def delete_many(self, filter_query: dict) -> FirestoreDeleteResult:
        if not self.client.is_connected():
            return FirestoreDeleteResult(0)

        fs_client = self.client.firestore_client
        col_ref = fs_client.collection(self.collection_name)
        # Handle regex pattern matching or prefix matching
        query = col_ref
        for field, val in filter_query.items():
            if isinstance(val, dict) and "$regex" in val:
                regex_pat = val["$regex"]
                if regex_pat.startswith("^"):
                    prefix = regex_pat[1:]
                    query = query.where(filter=FieldFilter(field, ">=", prefix)).where(filter=FieldFilter(field, "<=", prefix + "\uf8ff"))
            else:
                query = query.where(filter=FieldFilter(field, "==", val))

        count = 0
        snapshots = await query.get()
        for s in snapshots:
            await s.reference.delete()
            count += 1
        return FirestoreDeleteResult(count)

    async def count_documents(self, filter_query: Optional[dict] = None) -> int:
        if not self.client.is_connected():
            return 0
        fs_client = self.client.firestore_client
        col_ref = fs_client.collection(self.collection_name)
        try:
            # Modern Firestore count aggregation
            agg_query = col_ref.count()
            results = await agg_query.get()
            return int(results[0][0].value)
        except Exception:
            # Fallback stream count
            snapshots = await col_ref.get()
            return len(snapshots)

    async def create_index(self, keys: Any, unique: bool = False, **kwargs) -> str:
        """Acknowledge index declaration. In Firestore, composite indexes are declared in firestore.indexes.json."""
        logger.info(f"Firestore index definition registered for '{self.collection_name}': {keys} (unique={unique})")
        return f"{self.collection_name}_idx"


class FirestoreClient(BaseDatabaseClient):
    """
    Cloud Firestore Persistence Adapter for ChainVault.
    Provides async Firestore connectivity, collection wrappers, and atomic distributed transactions.
    """
    def __init__(self):
        self._client: Optional[AsyncClient] = None
        self._connected: bool = False

        self.project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT") or "chainvault-staging"
        self.database_id = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
        self.emulator_host = os.getenv("FIRESTORE_EMULATOR_HOST")
        self.credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        self.require_persistent_storage = (
            os.getenv("REQUIRE_PERSISTENT_STORAGE", "false").lower() in ("true", "1", "yes")
            or os.getenv("ENVIRONMENT", "development").lower() == "production"
        )

        self._adapters: Dict[str, FirestoreCollectionAdapter] = {}

    @property
    def client(self) -> Optional[AsyncClient]:
        return self._client

    @property
    def firestore_client(self) -> Optional[AsyncClient]:
        return self._client

    @property
    def db(self):
        return self

    def __getitem__(self, collection_name: str) -> FirestoreCollectionAdapter:
        if collection_name not in self._adapters:
            self._adapters[collection_name] = FirestoreCollectionAdapter(self, collection_name)
        return self._adapters[collection_name]

    @property
    def cases(self) -> FirestoreCollectionAdapter:
        return self["cases"]

    @property
    def evidence(self) -> FirestoreCollectionAdapter:
        return self["evidence"]

    @property
    def audit_logs(self) -> FirestoreCollectionAdapter:
        return self["audit_logs"]

    @property
    def custody_logs(self) -> FirestoreCollectionAdapter:
        return self["audit_logs"]

    @property
    def custody_transactions(self) -> FirestoreCollectionAdapter:
        return self["custody_transactions"]

    @property
    def idempotency_records(self) -> FirestoreCollectionAdapter:
        return self["idempotency_records"]

    @property
    def blockchain_checkpoints(self) -> FirestoreCollectionAdapter:
        return self["blockchain_checkpoints"]

    @property
    def reports(self) -> FirestoreCollectionAdapter:
        return self["reports"]

    @property
    def users(self) -> FirestoreCollectionAdapter:
        return self["users"]

    @property
    def tasks(self) -> FirestoreCollectionAdapter:
        return self["tasks"]

    async def connect(self) -> None:
        if not FIRESTORE_AVAILABLE:
            if self.require_persistent_storage:
                raise RuntimeError("google-cloud-firestore package is not installed but persistent storage is required.")
            logger.warning("google-cloud-firestore package unavailable; falling back to offline mode.")
            return

        try:
            # Determine emulator or service credentials
            if self.emulator_host:
                os.environ["FIRESTORE_EMULATOR_HOST"] = self.emulator_host
                self._client = AsyncClient(project=self.project_id, database=self.database_id)
            elif self.credentials_path and os.path.exists(self.credentials_path):
                self._client = AsyncClient.from_service_account_json(self.credentials_path, database=self.database_id)
            else:
                self._client = AsyncClient(project=self.project_id, database=self.database_id)

            # Verification probe
            self._connected = True
            logger.info(f"Initialized Firestore AsyncClient (project: {self.project_id}, database: {self.database_id}, emulator: {bool(self.emulator_host)})")
        except Exception as e:
            self._client = None
            self._connected = False
            logger.error(f"Failed to connect to Cloud Firestore: {e}")
            if self.require_persistent_storage:
                raise RuntimeError(f"Required persistent Firestore storage failed to connect: {e}")

    async def close(self) -> None:
        self._connected = False
        if self._client:
            close_fn = getattr(self._client, "close", None)
            if callable(close_fn):
                res = close_fn()
                if inspect.isawaitable(res):
                    await res
            self._client = None
            logger.info("Firestore client connection closed.")

    async def ping(self) -> bool:
        if not self.is_connected() or not self._client:
            return False
        try:
            # Lightweight probe
            agen = self._client.collections()
            await anext(agen, None)
            return True
        except Exception:
            return False

    def is_connected(self) -> bool:
        return bool(self._connected and self._client is not None)

    def get_persistence_mode(self) -> str:
        if self.is_connected():
            return "persistent" if self.require_persistent_storage else "hybrid_persistent"
        return "unavailable" if self.require_persistent_storage else "resilient_fallback"

    # =========================================================================
    # NATIVE FIRESTORE DISTRIBUTED CONCURRENCY & LEASE FENCING TRANSACTIONS
    # =========================================================================

    async def acquire_custody_transfer_lock(
        self,
        evidence_id: str,
        actor: str,
        idempotency_key: Optional[str] = None,
        lease_seconds: float = 30.0,
        wait_timeout: float = 0.4
    ) -> tuple[bool, Optional[str], Optional[str], int]:
        """
        Acquire distributed, atomic lease lock on an evidence document using Firestore transaction.
        Enforces optimistic concurrency control across multi-worker deployments.
        Returns: (acquired: bool, lock_token: Optional[str], reason: Optional[str], expected_version: int)
        """
        import uuid
        start_time = time.time()
        fs_client = self._client
        if not fs_client:
            return False, None, "UNAVAILABLE", 0

        doc_ref = fs_client.collection("evidence").document(evidence_id)

        while True:
            now = time.time()
            lock_token = uuid.uuid4().hex

            try:
                txn = fs_client.transaction()

                @async_transactional
                async def _txn_acquire(transaction):
                    snapshot = await doc_ref.get(transaction=transaction)
                    if not snapshot.exists:
                        return False, None, "NOT_FOUND", 0

                    data = snapshot.to_dict() or {}
                    curr_lock = data.get("transfer_lock") or {}
                    expected_version = data.get("custody_version", 0)

                    # Check if locked and unexpired
                    if curr_lock.get("status") == "LOCKED" and curr_lock.get("expires_at", 0) > now:
                        return False, None, "LOCKED", expected_version

                    lock_payload = {
                        "transfer_lock": {
                            "status": "LOCKED",
                            "actor": actor,
                            "lock_token": lock_token,
                            "idempotency_key": idempotency_key,
                            "locked_at": now,
                            "expires_at": now + lease_seconds,
                            "fencing_version": expected_version
                        }
                    }
                    transaction.update(doc_ref, lock_payload)
                    return True, lock_token, None, expected_version

                acquired, tok, reason, ver = await _txn_acquire(txn)
                if acquired:
                    return True, tok, None, ver
                if reason == "NOT_FOUND":
                    return False, None, "NOT_FOUND", 0
            except Exception as e:
                logger.debug(f"Firestore acquire lock transaction exception: {e}")

            if time.time() - start_time >= wait_timeout:
                return False, None, "LOCKED", 0
            await asyncio.sleep(0.02)

    async def renew_custody_transfer_lock(
        self,
        evidence_id: str,
        lock_token: str,
        additional_seconds: float = 30.0
    ) -> bool:
        """Safely extend lock lease duration using Firestore transaction."""
        fs_client = self._client
        if not fs_client:
            return False
        doc_ref = fs_client.collection("evidence").document(evidence_id)
        now = time.time()

        try:
            txn = fs_client.transaction()

            @async_transactional
            async def _txn_renew(transaction):
                snapshot = await doc_ref.get(transaction=transaction)
                if not snapshot.exists:
                    return False
                data = snapshot.to_dict() or {}
                curr_lock = data.get("transfer_lock") or {}
                if curr_lock.get("lock_token") != lock_token or curr_lock.get("status") != "LOCKED":
                    return False
                transaction.update(doc_ref, {"transfer_lock.expires_at": now + additional_seconds})
                return True

            return await _txn_renew(txn)
        except Exception:
            return False

    async def release_custody_transfer_lock(
        self,
        evidence_id: str,
        lock_token: Optional[str] = None,
        new_custodian: Optional[str] = None,
        expected_version: Optional[int] = None,
        failed: bool = False,
        err_msg: Optional[str] = None
    ) -> bool:
        """
        Release atomic lease lock and CAS update custodian using fencing version verification.
        Guarantees that stale workers whose leases expired cannot overwrite active state.
        """
        fs_client = self._client
        if not fs_client:
            return False
        doc_ref = fs_client.collection("evidence").document(evidence_id)
        now = time.time()

        try:
            txn = fs_client.transaction()

            @async_transactional
            async def _txn_release(transaction):
                snapshot = await doc_ref.get(transaction=transaction)
                if not snapshot.exists:
                    return False
                data = snapshot.to_dict() or {}
                curr_lock = data.get("transfer_lock") or {}
                current_ver = data.get("custody_version", 0)

                # 1. Lock token verification
                if lock_token and curr_lock.get("lock_token") != lock_token:
                    return False

                # 2. Fencing version verification
                if not failed and expected_version is not None:
                    if current_ver != expected_version:
                        return False

                updates: dict = {
                    "transfer_lock.status": "FAILED" if failed else "UNLOCKED",
                    "transfer_lock.released_at": now
                }
                if err_msg:
                    updates["transfer_lock.error"] = err_msg
                if not failed and new_custodian:
                    updates["custodian"] = new_custodian
                if not failed:
                    updates["custody_version"] = firestore.Increment(1)

                transaction.update(doc_ref, updates)
                return True

            return await _txn_release(txn)
        except Exception as e:
            logger.debug(f"Firestore release lock transaction exception: {e}")
            return False
