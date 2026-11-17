from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

import asyncio
from typing import Optional

from .base import BaseDatabaseClient

class MongoDBClient(BaseDatabaseClient):
    def __init__(self):
        self._client = None
        self._db = None
        self._connected = False
        self._bound_loop = None

        self._users_override = None
        self._cases_override = None
        self._evidence_override = None
        self._custody_logs_override = None
        self._audit_logs_override = None
        self._reports_override = None
        self._checkpoints_override = None
        self._tasks_override = None

        # Load from environment variables
        self.uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = os.getenv("MONGO_DB_NAME", "chainvault")
        self.require_persistent_storage = (
            os.getenv("REQUIRE_PERSISTENT_STORAGE", "false").lower() in ("true", "1", "yes")
            or os.getenv("ENVIRONMENT", "development").lower() == "production"
        )

    def _ensure_active_loop_client(self):
        """Ensure AsyncIOMotorClient is bound to the currently running event loop without touching closed loops."""
        if not self._connected:
            return self._client
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if current_loop is not None:
            if (self._client is None or self._bound_loop is None or self._bound_loop.is_closed() or self._bound_loop != current_loop):
                self._client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=2000)
                self._db = self._client[self.db_name]
                self._bound_loop = current_loop
        return self._client

    @property
    def client(self):
        return self._ensure_active_loop_client()

    @client.setter
    def client(self, val):
        self._client = val
        self._bound_loop = None
        if val is None:
            self._connected = False

    @property
    def db(self):
        self._ensure_active_loop_client()
        return self._db

    @db.setter
    def db(self, val):
        self._db = val
        if val is None:
            self._connected = False

    @property
    def users(self):
        if self._users_override is not None:
            return self._users_override
        d = self.db
        return d["users"] if d is not None else None

    @users.setter
    def users(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._users_override = None
        else:
            self._users_override = val

    @property
    def cases(self):
        if self._cases_override is not None:
            return self._cases_override
        d = self.db
        return d["cases"] if d is not None else None

    @cases.setter
    def cases(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._cases_override = None
        else:
            self._cases_override = val

    @property
    def evidence(self):
        if self._evidence_override is not None:
            return self._evidence_override
        d = self.db
        return d["evidence"] if d is not None else None

    @evidence.setter
    def evidence(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._evidence_override = None
        else:
            self._evidence_override = val

    @property
    def custody_logs(self):
        if self._custody_logs_override is not None:
            return self._custody_logs_override
        d = self.db
        return d["custody_logs"] if d is not None else None

    @custody_logs.setter
    def custody_logs(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._custody_logs_override = None
        else:
            self._custody_logs_override = val

    @property
    def audit_logs(self):
        if self._audit_logs_override is not None:
            return self._audit_logs_override
        d = self.db
        return d["audit_logs"] if d is not None else None

    @audit_logs.setter
    def audit_logs(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._audit_logs_override = None
        else:
            self._audit_logs_override = val

    @property
    def reports(self):
        if self._reports_override is not None:
            return self._reports_override
        d = self.db
        return d["reports"] if d is not None else None

    @reports.setter
    def reports(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._reports_override = None
        else:
            self._reports_override = val

    @property
    def blockchain_checkpoints(self):
        if self._checkpoints_override is not None:
            return self._checkpoints_override
        d = self.db
        return d["blockchain_checkpoints"] if d is not None else None

    @blockchain_checkpoints.setter
    def blockchain_checkpoints(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._checkpoints_override = None
        else:
            self._checkpoints_override = val

    @property
    def custody_transactions(self):
        if hasattr(self, "_custody_transactions_override") and self._custody_transactions_override is not None:
            return self._custody_transactions_override
        d = self.db
        return d["custody_transactions"] if d is not None else None

    @custody_transactions.setter
    def custody_transactions(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._custody_transactions_override = None
        else:
            self._custody_transactions_override = val

    @property
    def tasks(self):
        if self._tasks_override is not None:
            return self._tasks_override
        d = self.db
        return d["tasks"] if d is not None else None

    @tasks.setter
    def tasks(self, val):
        if val is None or isinstance(val, AsyncIOMotorCollection):
            self._tasks_override = None
        else:
            self._tasks_override = val


    async def connect(self):
        try:
            self._connected = True
            c = self._ensure_active_loop_client()
            d = self.db

            # Ensure indexes across collections
            try:
                await d["audit_logs"].create_index([("evidence_id", 1), ("sequence_number", 1)], unique=True)
                await d["audit_logs"].create_index("event_id", unique=True)
                await d["evidence"].create_index("evidence_id", unique=True)
                await d["cases"].create_index("case_id", unique=True)
                await d["blockchain_checkpoints"].create_index("checkpoint_id", unique=True)
                await d["reports"].create_index("report_id", unique=True)
                await d["idempotency_records"].create_index("idempotency_key", unique=True)
                await d["custody_transactions"].create_index("transaction_id", unique=True)
                await d["custody_transactions"].create_index("idempotency_key", unique=True, sparse=True)
                await d["custody_transactions"].create_index([("evidence_id", 1), ("status", 1)])
                await d["tasks"].create_index("task_id", unique=True)
                await d["tasks"].create_index([("assigned_to_username", 1), ("status", 1)])
            except Exception as e:
                logger.debug(f"Collection index initialization skipped/existing: {e}")

            # Verify connection with ping
            await c.admin.command('ping')
            logger.info(f"Successfully connected to MongoDB ({self.db_name}). Persistence mode: {self.get_persistence_mode()}")
        except Exception as e:
            logger.error(f"Could not connect to MongoDB: {e}")
            self._client = None
            self._db = None
            self._connected = False
            self._bound_loop = None
            if self.require_persistent_storage:
                raise RuntimeError(f"Required persistent storage failed to connect: {e}")

    def is_connected(self) -> bool:
        """Check if MongoDB client is initialized and active."""
        return bool(self._connected and self._client is not None and self._db is not None)


    async def ping(self) -> bool:
        """Verify live MongoDB connection responsiveness."""
        if not self.is_connected():
            return False
        try:
            res = await self.client.admin.command('ping')
            return res.get('ok') == 1.0
        except Exception:
            return False

    def get_persistence_mode(self) -> str:
        """Return diagnostic persistence status."""
        if self.is_connected():
            return "persistent" if self.require_persistent_storage else "hybrid_persistent"
        return "unavailable" if self.require_persistent_storage else "resilient_fallback"

    def safeguard_test_database(self, operation: str = "destructive"):
        """
        Automated safety guard: Rejects destructive test operations
        (e.g., drop, bulk reset, purge) unless the active database is strictly 'chainvault_test'.
        """
        if self.db_name != "chainvault_test":
            raise PermissionError(
                f"Destructive operation '{operation}' rejected: active database is '{self.db_name}', "
                f"not the designated test database 'chainvault_test'."
            )

    async def drop_test_database(self):
        """
        Safely drop test database after verifying safety guard.
        Raises PermissionError if active database is development or production.
        """
        self.safeguard_test_database("drop_test_database")
        if self.client and self.db:
            await self.client.drop_database(self.db_name)
            logger.info(f"Test database '{self.db_name}' dropped successfully.")

    async def close(self):
        self._connected = False
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB connection closed.")

def get_database_client(backend: Optional[str] = None) -> BaseDatabaseClient:
    target_backend = (backend or os.getenv("DATABASE_BACKEND", "mongodb")).lower().strip()
    if target_backend == "firestore":
        from .firestore import FirestoreClient
        return FirestoreClient()
    return MongoDBClient()

_active_backend = os.getenv("DATABASE_BACKEND", "mongodb").lower().strip()
if _active_backend == "firestore":
    from .firestore import FirestoreClient
    db_client = FirestoreClient()
else:
    db_client = MongoDBClient()
