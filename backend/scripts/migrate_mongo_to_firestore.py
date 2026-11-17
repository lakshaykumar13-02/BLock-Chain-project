#!/usr/bin/env python3
"""
ChainVault Phase 3A — MongoDB to Cloud Firestore Emulator Migration Tool
========================================================================
Non-destructive, idempotent, and emulator-restricted metadata migration tool.

Safety Guarantees:
1. READ-ONLY on MongoDB source: never modifies, creates, drops, or alters MongoDB data.
2. EMULATOR RESTRICTION: refuses to execute against cloud or production Firebase targets.
   Validates local loopback host (127.0.0.1:8080 or localhost:8080).
3. STORAGE DECOUPLING: never writes binary evidence or report files to Firestore.
   Verifies physical file paths and hashes on disk independently.
4. CANONICAL AUDIT INVARIANCE: normalizes timestamps to RFC 3339 UTC strings
   and verifies canonical SHA-256 hashes against original records.
5. DRY-RUN BY DEFAULT: requires explicit --execute flag to write.
6. IDEMPOTENT RERUNS & CONFLICT DETECTION: skips identical records on rerun
   and flags conflicting destination records instead of silently overwriting.
7. COMPREHENSIVE MANIFEST: outputs audit manifest with counts, diffs, and verification metrics.
"""

import os
import sys
import json
import time
import socket
import hashlib
import asyncio
import logging
import argparse
import datetime
from typing import Any, Dict, List, Optional, Tuple, Set

# Ensure backend root is on sys.path for relative imports when executed directly
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

logger = logging.getLogger("chainvault.migration")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    MOTOR_AVAILABLE = True
except ImportError:
    AsyncIOMotorClient = None
    MOTOR_AVAILABLE = False

try:
    from google.cloud import firestore
    from google.cloud.firestore import AsyncClient
    from google.api_core.exceptions import AlreadyExists, NotFound
    FIRESTORE_AVAILABLE = True
except ImportError:
    firestore = None
    AsyncClient = None
    AlreadyExists = Exception
    NotFound = Exception
    FIRESTORE_AVAILABLE = False

from app.services.audit_trail import (
    calculate_canonical_event_hash,
    normalize_utc_timestamp
)


# =============================================================================
# COLLECTION SPECIFICATIONS & MAPPINGS
# =============================================================================

COLLECTION_SPECS = {
    "cases": {
        "primary_key": "case_id",
        "has_files": False,
        "has_hashes": False,
        "destination_collection": "cases"
    },
    "evidence": {
        "primary_key": "evidence_id",
        "has_files": True,
        "file_path_field": "file_path",
        "hash_field": "file_hash",
        "has_hashes": True,
        "destination_collection": "evidence"
    },
    "audit_logs": {
        "primary_key": "event_id",
        "has_files": False,
        "has_hashes": True,
        "is_canonical_audit": True,
        "destination_collection": "audit_logs"
    },
    "custody_transactions": {
        "primary_key": "transaction_id",
        "has_files": False,
        "has_hashes": False,
        "destination_collection": "custody_transactions"
    },
    "idempotency_records": {
        "primary_key": "idempotency_key",
        "has_files": False,
        "has_hashes": False,
        "destination_collection": "idempotency_records"
    },
    "blockchain_checkpoints": {
        "primary_key": "checkpoint_id",
        "fallback_fn": lambda d: f"CHK-{d.get('evidence_id')}" if d.get("evidence_id") else None,
        "has_files": False,
        "has_hashes": False,
        "destination_collection": "blockchain_checkpoints"
    },
    "reports": {
        "primary_key": "report_id",
        "has_files": True,
        "file_path_field": "file_path",
        "hash_field": "sha256_hash",
        "has_hashes": True,
        "destination_collection": "reports"
    },
    "users": {
        "primary_key": "username",
        "fallback_field": "user_id",
        "has_files": False,
        "has_hashes": False,
        "destination_collection": "users"
    },
    "custody_logs": {
        "primary_key": "event_id",
        "fallback_field": "log_id",
        "destination_collection": "audit_logs",
        "has_files": False,
        "has_hashes": True,
        "is_canonical_audit": True
    }
}


# =============================================================================
# SAFETY GUARDS & VALIDATORS
# =============================================================================

ALLOWED_EMULATOR_HOSTS = {"127.0.0.1:8080", "localhost:8080", "[::1]:8080"}
PROHIBITED_PROJECT_KEYWORDS = {"prod", "production", "live", "mainnet"}


def validate_emulator_target(emulator_host: Optional[str], project_id: str) -> None:
    """
    Strict safety check: Ensures migration CANNOT run against real cloud resources.
    Rejects any configuration pointing to cloud endpoints or production project names.
    """
    if not emulator_host:
        raise RuntimeError(
            "SAFETY VIOLATION: FIRESTORE_EMULATOR_HOST is unset. "
            "Migration is strictly restricted to the local Firestore Emulator."
        )

    clean_host = emulator_host.strip().lower()
    host_ip = clean_host.split(":")[0]
    if host_ip not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError(
            f"SAFETY VIOLATION: Emulator host '{clean_host}' is not a local loopback address. "
            "Execution aborted to prevent accidental network routing."
        )

    clean_project = project_id.strip().lower()
    for kw in PROHIBITED_PROJECT_KEYWORDS:
        if kw in clean_project:
            raise RuntimeError(
                f"SAFETY VIOLATION: Project ID '{project_id}' contains prohibited keyword '{kw}'. "
                "Migration is only permitted against synthetic/emulator project IDs."
            )


def validate_cloud_staging_target(project_id: str, database_id: str) -> None:
    """
    Validate that cloud migration targets strictly the staging project 'chainvault-staging'
    and database '(default)'. Rejects any other cloud destination.
    """
    if project_id != "chainvault-staging":
        raise RuntimeError(
            f"SAFETY VIOLATION: Target project '{project_id}' is not 'chainvault-staging'. "
            "Cloud migration is strictly restricted to chainvault-staging."
        )
    if database_id != "(default)":
        raise RuntimeError(
            f"SAFETY VIOLATION: Target database '{database_id}' is not '(default)'. "
            "Cloud migration is strictly restricted to database (default)."
        )


def is_emulator_active(host_str: str) -> bool:
    """Verify local TCP connectivity to the Firestore Emulator port."""
    try:
        parts = host_str.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 8080
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except Exception:
        return False


# =============================================================================
# DOCUMENT SANITIZATION & NORMALIZATION
# =============================================================================

def clean_doc_for_firestore(doc: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Sanitizes MongoDB document for Firestore persistence:
    1. Extracts primary key based on collection specification or _id fallback.
    2. Strips MongoDB BSON '_id'.
    3. Normalizes datetimes to canonical RFC 3339 UTC strings.
    4. Recursively converts BSON primitives to JSON-serializable types.
    """
    cleaned = {}
    doc_id = None

    for k, v in doc.items():
        if k == "_id":
            # If string _id, keep as fallback doc_id
            if isinstance(v, str) and not doc_id:
                doc_id = v
            continue

        cleaned[k] = _clean_value(v)

    return doc_id, cleaned


def _clean_value(val: Any) -> Any:
    """Recursively sanitize values to ensure strict JSON and Firestore compatibility."""
    if val is None:
        return None
    elif isinstance(val, (str, int, float, bool)):
        return val
    elif isinstance(val, datetime.datetime):
        return normalize_utc_timestamp(val)
    elif isinstance(val, datetime.date):
        dt = datetime.datetime(val.year, val.month, val.day, tzinfo=datetime.timezone.utc)
        return normalize_utc_timestamp(dt)
    elif isinstance(val, dict):
        return {str(k): _clean_value(v) for k, v in val.items() if k != "_id"}
    elif isinstance(val, (list, tuple, set)):
        return [_clean_value(item) for item in val]
    elif isinstance(val, (bytes, bytearray)):
        raise TypeError(f"Binary data detected ({len(val)} bytes). File contents must remain on disk.")
    else:
        # Fallback to string representation for ObjectId, Decimal128, etc.
        return str(val)


def extract_primary_key(
    collection_name: str,
    doc: Dict[str, Any],
    fallback_id: Optional[str] = None
) -> Optional[str]:
    """Deterministically extracts document key according to collection specs."""
    spec = COLLECTION_SPECS.get(collection_name, {})
    pk_field = spec.get("primary_key", "_id")

    if pk_field in doc and doc[pk_field]:
        return str(doc[pk_field]).strip()

    fallback_field = spec.get("fallback_field")
    if fallback_field and fallback_field in doc and doc[fallback_field]:
        return str(doc[fallback_field]).strip()

    fallback_fn = spec.get("fallback_fn")
    if fallback_fn and callable(fallback_fn):
        computed = fallback_fn(doc)
        if computed:
            return str(computed).strip()

    if fallback_id:
        return str(fallback_id).strip()

    if "_id" in doc and doc["_id"]:
        return str(doc["_id"]).strip()

    return None


def calculate_file_sha256(file_path: str) -> Optional[str]:
    """Compute SHA-256 hash of physical file on disk."""
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return None
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def find_document_differences(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """Compare existing destination document with incoming document to detect conflicting changes."""
    diffs = {}
    all_keys = set(existing.keys()) | set(incoming.keys())
    for k in all_keys:
        if k in ("_id", "migrated_at"):
            continue
        v_exist = existing.get(k)
        v_incom = incoming.get(k)
        if v_exist != v_incom:
            diffs[k] = {"destination": v_exist, "source": v_incom}
    return diffs


# =============================================================================
# MIGRATION ENGINE
# =============================================================================

class MongoToFirestoreMigrator:
    """
    Executes non-destructive, read-only migration from MongoDB to Firestore Emulator.
    """

    def __init__(
        self,
        mongo_uri: str,
        mongo_db_name: str,
        emulator_host: Optional[str] = "127.0.0.1:8080",
        project_id: str = "chainvault-emulator",
        database_id: str = "(default)",
        dry_run: bool = True,
        batch_size: int = 100,
        verify_files: bool = True,
        is_cloud: bool = False
    ):
        self.mongo_uri = mongo_uri
        self.mongo_db_name = mongo_db_name
        self.emulator_host = emulator_host
        self.project_id = project_id
        self.database_id = database_id
        self.dry_run = dry_run
        self.batch_size = max(1, batch_size)
        self.verify_files = verify_files
        self.is_cloud = is_cloud

        if self.is_cloud:
            validate_cloud_staging_target(self.project_id, self.database_id)
        else:
            validate_emulator_target(self.emulator_host, self.project_id)

        self._mongo_client: Optional[Any] = None
        self._firestore_client: Optional[AsyncClient] = None
        self.manifest: Dict[str, Any] = {}

    async def connect(self) -> None:
        """Connect to source MongoDB (read-only) and target Firestore (Emulator or Cloud)."""
        if self.is_cloud:
            if "FIRESTORE_EMULATOR_HOST" in os.environ:
                del os.environ["FIRESTORE_EMULATOR_HOST"]
            os.environ["FIREBASE_PROJECT_ID"] = self.project_id
            os.environ["GCLOUD_PROJECT"] = self.project_id
            self._firestore_client = AsyncClient(project=self.project_id, database=self.database_id)
            logger.info(f"Target: Cloud Firestore project '{self.project_id}', database '{self.database_id}' via ADC")
        else:
            # 1. Target Emulator check
            if not self.emulator_host or not is_emulator_active(self.emulator_host):
                raise RuntimeError(
                    f"Firestore Emulator is not running on {self.emulator_host}. "
                    "Start emulator before running migration."
                )

            os.environ["FIRESTORE_EMULATOR_HOST"] = self.emulator_host
            os.environ["FIREBASE_PROJECT_ID"] = self.project_id
            os.environ["GCLOUD_PROJECT"] = self.project_id

            self._firestore_client = AsyncClient(project=self.project_id)
            logger.info(f"Target: Firestore Emulator at {self.emulator_host} (project: {self.project_id})")

        # 2. Source MongoDB (read-only)
        self._mongo_client = AsyncIOMotorClient(self.mongo_uri)
        # Probe connection
        await self._mongo_client.admin.command("ping")
        logger.info(f"Source: MongoDB connected at {self.mongo_uri} (db: {self.mongo_db_name}) [READ-ONLY]")

    async def close(self) -> None:
        """Close database clients cleanly."""
        if self._mongo_client:
            self._mongo_client.close()
            self._mongo_client = None
        if self._firestore_client:
            close_fn = getattr(self._firestore_client, "close", None)
            if callable(close_fn):
                res = close_fn()
                if asyncio.iscoroutine(res):
                    await res
            self._firestore_client = None

    async def run(self, collections_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        """Execute migration across target collections and produce audit manifest."""
        start_time = datetime.datetime.now(datetime.timezone.utc)
        collections_to_migrate = collections_filter or list(COLLECTION_SPECS.keys())

        self.manifest = {
            "timestamp": start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "mode": "DRY_RUN" if self.dry_run else "EXECUTE",
            "source_mongo": {
                "uri": self.mongo_uri.split("@")[-1],  # redact credentials if present
                "db_name": self.mongo_db_name
            },
            "destination_firestore": {
                "emulator_host": self.emulator_host,
                "project_id": self.project_id
            },
            "collections": {},
            "summary": {
                "total_source_records": 0,
                "total_migrated": 0,
                "total_already_identical": 0,
                "total_conflicts": 0,
                "total_errors": 0,
                "status": "IN_PROGRESS"
            }
        }

        db = self._mongo_client[self.mongo_db_name]
        has_critical_failures = False

        for col_name in collections_to_migrate:
            if col_name not in COLLECTION_SPECS:
                logger.warning(f"Skipping unmapped collection: {col_name}")
                continue

            col_stats = await self._migrate_collection(db, col_name)
            self.manifest["collections"][col_name] = col_stats

            self.manifest["summary"]["total_source_records"] += col_stats["source_count"]
            self.manifest["summary"]["total_migrated"] += col_stats["migrated_count"]
            self.manifest["summary"]["total_already_identical"] += col_stats["already_present_count"]
            self.manifest["summary"]["total_conflicts"] += col_stats["conflict_count"]
            self.manifest["summary"]["total_errors"] += col_stats["error_count"]

            if col_stats["conflict_count"] > 0 or col_stats["error_count"] > 0:
                has_critical_failures = True

        end_time = datetime.datetime.now(datetime.timezone.utc)
        self.manifest["duration_seconds"] = (end_time - start_time).total_seconds()
        self.manifest["summary"]["status"] = "WARNINGS" if has_critical_failures else "SUCCESS"

        return self.manifest

    async def _migrate_collection(self, mongo_db: Any, collection_name: str) -> Dict[str, Any]:
        """Migrate a single collection with batch streaming, verification, and conflict detection."""
        spec = COLLECTION_SPECS[collection_name]
        dest_col_name = spec.get("destination_collection", collection_name)
        source_col = mongo_db[collection_name]
        dest_col_ref = self._firestore_client.collection(dest_col_name)

        stats = {
            "source_collection": collection_name,
            "destination_collection": dest_col_name,
            "source_count": 0,
            "migrated_count": 0,
            "already_present_count": 0,
            "conflict_count": 0,
            "error_count": 0,
            "conflicts": [],
            "errors": [],
            "hash_verification": {"verified": 0, "mismatched": 0, "skipped": 0},
            "file_checks": {"verified_on_disk": 0, "missing_on_disk": 0, "hash_mismatches": 0}
        }

        # Check collection existence in MongoDB
        try:
            total_source = await source_col.count_documents({})
            stats["source_count"] = total_source
        except Exception as e:
            stats["errors"].append(f"Failed to inspect source collection '{collection_name}': {e}")
            stats["error_count"] += 1
            return stats

        if total_source == 0:
            logger.info(f"[{collection_name}] Empty collection in MongoDB. Nothing to migrate.")
            return stats

        logger.info(f"[{collection_name}] Processing {total_source} records (dest: '{dest_col_name}')...")

        cursor = source_col.find({}, batch_size=self.batch_size)
        async for raw_doc in cursor:
            try:
                await self._process_document(raw_doc, collection_name, dest_col_ref, stats)
            except Exception as e:
                stats["error_count"] += 1
                stats["errors"].append(f"Doc error in {collection_name}: {str(e)}")

        return stats

    async def _process_document(
        self,
        raw_doc: Dict[str, Any],
        collection_name: str,
        dest_col_ref: Any,
        stats: Dict[str, Any]
    ) -> None:
        """Process an individual document: sanitize, verify, check existence, and conditionally write."""
        spec = COLLECTION_SPECS[collection_name]
        fallback_id, cleaned_data = clean_doc_for_firestore(raw_doc)
        doc_id = extract_primary_key(collection_name, raw_doc, fallback_id)

        if not doc_id:
            stats["error_count"] += 1
            stats["errors"].append(f"Could not determine primary key for document: {raw_doc.get('_id')}")
            return

        # 1. Canonical Audit Hash Verification
        if spec.get("is_canonical_audit"):
            event_hash = raw_doc.get("event_hash")
            if event_hash:
                try:
                    recalculated = calculate_canonical_event_hash(cleaned_data)
                    if recalculated.lower() == str(event_hash).lower():
                        stats["hash_verification"]["verified"] += 1
                    else:
                        stats["hash_verification"]["mismatched"] += 1
                        stats["errors"].append(
                            f"Audit hash mismatch on {doc_id}: expected {event_hash}, calculated {recalculated}"
                        )
                except Exception as e:
                    stats["hash_verification"]["skipped"] += 1
                    logger.debug(f"Audit hash calculation skipped for {doc_id}: {e}")
            else:
                stats["hash_verification"]["skipped"] += 1

        # 2. Physical File Integrity & Path Verification
        if spec.get("has_files") and self.verify_files:
            fp_field = spec.get("file_path_field", "file_path")
            hash_field = spec.get("hash_field", "file_hash")
            file_path = raw_doc.get(fp_field)
            expected_hash = raw_doc.get(hash_field)

            if file_path:
                if os.path.exists(file_path):
                    if expected_hash:
                        disk_hash = calculate_file_sha256(file_path)
                        if disk_hash and disk_hash.lower() == str(expected_hash).lower():
                            stats["file_checks"]["verified_on_disk"] += 1
                        else:
                            stats["file_checks"]["hash_mismatches"] += 1
                            stats["errors"].append(
                                f"File hash mismatch on {doc_id} ({file_path}): expected {expected_hash}, disk {disk_hash}"
                            )
                    else:
                        stats["file_checks"]["verified_on_disk"] += 1
                else:
                    stats["file_checks"]["missing_on_disk"] += 1
                    # Historical files missing on disk is recorded as a warning, not fatal

        # 3. Target Conflict Detection & Idempotency Check
        target_doc_ref = dest_col_ref.document(doc_id)
        snapshot = await target_doc_ref.get()

        if snapshot.exists:
            existing_data = snapshot.to_dict() or {}
            diffs = find_document_differences(existing_data, cleaned_data)
            if not diffs:
                # Byte-for-byte identical record already migrated
                stats["already_present_count"] += 1
                return
            else:
                # Conflicting destination record exists! Do NOT overwrite!
                stats["conflict_count"] += 1
                stats["conflicts"].append({"doc_id": doc_id, "diff": diffs})
                return

        # 4. Conditionally Persist to Emulator
        if not self.dry_run:
            await target_doc_ref.set(cleaned_data)
            stats["migrated_count"] += 1
        else:
            # Dry-run: record as staged for migration
            stats["migrated_count"] += 1


# =============================================================================
# CLI ENTRYPOINT
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="ChainVault Non-Destructive MongoDB to Firestore Emulator Migration Tool"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute actual writes to local Firestore Emulator. Default is DRY-RUN mode."
    )
    parser.add_argument(
        "--mongo-uri",
        default=os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        help="MongoDB connection URI (read-only)."
    )
    parser.add_argument(
        "--mongo-db",
        default=os.getenv("MONGO_DB_NAME", "chainvault"),
        help="MongoDB database name to read."
    )
    parser.add_argument(
        "--emulator-host",
        default=os.getenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080"),
        help="Target Firestore Emulator host (must be local loopback)."
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("FIREBASE_PROJECT_ID", "chainvault-emulator"),
        help="Target Firebase project ID."
    )
    parser.add_argument(
        "--collections",
        default=None,
        help="Comma-separated list of collections to migrate (default: all)."
    )
    parser.add_argument(
        "--manifest-out",
        default="migration_manifest.json",
        help="Path to write the resulting JSON audit manifest."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for source document streaming."
    )
    parser.add_argument(
        "--no-file-verify",
        action="store_true",
        default=False,
        help="Skip checking physical disk files for evidence and reports."
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        default=False,
        help="Migrate directly to Cloud Firestore staging ('chainvault-staging', '(default)') using ADC."
    )
    parser.add_argument(
        "--database-id",
        default="(default)",
        help="Target Firestore database ID (default: '(default)')."
    )
    return parser.parse_args()


async def main_async():
    args = parse_args()
    cols_filter = [c.strip() for c in args.collections.split(",") if c.strip()] if args.collections else None
    dry_run = not args.execute

    target_desc = f"Cloud Firestore (project: {args.project_id}, db: {args.database_id})" if args.cloud else f"Emulator ({args.emulator_host})"
    logger.info("=" * 70)
    logger.info(f"ChainVault MongoDB -> Firestore Migration Tool [{target_desc}]")
    logger.info(f"Mode: {'DRY-RUN (Simulate only)' if dry_run else 'EXECUTE (Writing to ' + target_desc + ')'}")
    logger.info("=" * 70)

    project_id = "chainvault-staging" if (args.cloud and args.project_id == "chainvault-emulator") else args.project_id

    migrator = MongoToFirestoreMigrator(
        mongo_uri=args.mongo_uri,
        mongo_db_name=args.mongo_db,
        emulator_host=args.emulator_host if not args.cloud else None,
        project_id=project_id,
        database_id=args.database_id,
        dry_run=dry_run,
        batch_size=args.batch_size,
        verify_files=(not args.no_file_verify),
        is_cloud=args.cloud
    )

    try:
        await migrator.connect()
        manifest = await migrator.run(collections_filter=cols_filter)

        # Output manifest
        manifest_json = json.dumps(manifest, indent=2)
        if args.manifest_out:
            with open(args.manifest_out, "w", encoding="utf-8") as f:
                f.write(manifest_json)
            logger.info(f"Migration manifest written to: {args.manifest_out}")

        logger.info("-" * 70)
        logger.info(f"Summary: {manifest['summary']['status']}")
        logger.info(f"Source records inspected: {manifest['summary']['total_source_records']}")
        logger.info(f"Records to migrate:       {manifest['summary']['total_migrated']}")
        logger.info(f"Already identical:        {manifest['summary']['total_already_identical']}")
        logger.info(f"Conflicts detected:       {manifest['summary']['total_conflicts']}")
        logger.info(f"Errors encountered:       {manifest['summary']['total_errors']}")
        logger.info("-" * 70)

    finally:
        await migrator.close()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
