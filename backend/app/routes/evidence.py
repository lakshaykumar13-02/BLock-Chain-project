import os
import datetime
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from ..services.hashing import calculate_hash
from ..services.storage import save_file, get_file_path
from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..database.mongodb import db_client
from ..services.task_service import get_employee_authorized_resources

router = APIRouter(prefix="/evidence", tags=["Evidence"])

# In-memory storage for resilient testing & development fallback
EVIDENCE_STORE: dict[str, dict] = {}

class EvidenceResponse(BaseModel):
    evidence_id: str
    case_id: str
    filename: str
    file_hash: str
    file_size: int
    custodian: str
    uploaded_at: str
    blockchain_registered: bool = False
    blockchain_tx: Optional[str] = None

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    file: Optional[UploadFile] = File(None),
    case_id: Optional[str] = Form("CV-2026-001"),
    evidence_id: Optional[str] = Form(None),
    custodian: Optional[str] = Form(None),
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """
    Ingest forensic evidence, compute SHA-256 hash, and persist metadata.
    Allowed roles: ADMIN, INVESTIGATOR.
    Evidence deletion is strictly forbidden to preserve immutable chain of custody.
    """
    # Enforce persistent database requirement
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent database storage is required but currently unavailable"
        )

    effective_custodian = custodian or current_user.get("username", "investigator1")

    if file is None:
        assigned_id = evidence_id or f"EV-{len(EVIDENCE_STORE) + 1:03d}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        dummy_hash = calculate_hash(b"")
        record = {
            "evidence_id": assigned_id,
            "case_id": case_id or "CV-2026-001",
            "filename": "empty_evidence.bin",
            "file_hash": dummy_hash,
            "file_size": 0,
            "file_path": "",
            "custodian": effective_custodian,
            "uploaded_at": now,
            "blockchain_registered": False,
            "blockchain_tx": None
        }
        if db_client.is_connected():
            try:
                doc = {k: v for k, v in record.items() if k != "_id"}
                await db_client.evidence.update_one({"evidence_id": assigned_id}, {"$set": doc}, upsert=True)
            except Exception as e:
                if db_client.require_persistent_storage:
                    raise HTTPException(status_code=500, detail=f"Database persistent write failed: {str(e)}")
        elif db_client.require_persistent_storage:
            raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")

        EVIDENCE_STORE[assigned_id] = record
        from ..services.audit_trail import record_custody_event
        await record_custody_event(
            evidence_id=assigned_id,
            action="EVIDENCE_INGESTION",
            actor_id=effective_custodian,
            case_id=record["case_id"],
            details={
                "file_hash": dummy_hash,
                "filename": "empty_evidence.bin",
                "file_size": 0,
                "previous_custodian": "None",
                "new_custodian": effective_custodian,
                "reason": "Initial digital evidence ingestion"
            },
            custom_timestamp=now
        )
        return record

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload stream read error: {str(e)}")

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File size exceeds maximum allowed limit (50MB)"
        )

    raw_filename = file.filename or "evidence.bin"
    forbidden_chars = ['\x00', '\n', '\r', '<', '>', ':', '"', '/', '\\', '|', '?', '*']
    if any(c in raw_filename for c in forbidden_chars) or ".." in raw_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: contains unexpected or forbidden characters"
        )

    file_hash = calculate_hash(content)
    try:
        stored_name, file_path, file_size = save_file(raw_filename, content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage filesystem write error: {str(e)}")

    assigned_id = evidence_id or f"EV-{len(EVIDENCE_STORE) + 1:03d}"

    # Check duplicate existence in MongoDB or memory store
    existing = None
    if db_client.is_connected():
        try:
            existing = await db_client.evidence.find_one({"evidence_id": assigned_id})
        except Exception:
            pass
    if not existing:
        existing = EVIDENCE_STORE.get(assigned_id)

    if existing:
        if existing.get("file_hash", "").lower() != file_hash.lower():
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Evidence ID '{assigned_id}' already exists with different file hash. Overwrite forbidden."
            )
        else:
            old_fp = existing.get("file_path", "")
            if not old_fp or not os.path.exists(old_fp):
                existing["file_path"] = file_path
                existing["stored_filename"] = stored_name
                if db_client.is_connected():
                    try:
                        await db_client.evidence.update_one(
                            {"evidence_id": assigned_id},
                            {"$set": {"file_path": file_path, "stored_filename": stored_name}}
                        )
                    except Exception:
                        pass
            else:
                if os.path.exists(file_path) and file_path != old_fp:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
            EVIDENCE_STORE[assigned_id] = existing
            return {
                "status": "success",
                "evidence_id": assigned_id,
                "case_id": existing["case_id"],
                "filename": existing["filename"],
                "file_hash": existing["file_hash"],
                "file_size": existing["file_size"],
                "uploaded_at": existing["uploaded_at"]
            }


    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    record = {
        "evidence_id": assigned_id,
        "case_id": case_id or "CV-2026-001",
        "filename": file.filename or "evidence.bin",
        "stored_filename": stored_name,
        "file_hash": file_hash,
        "file_size": file_size,
        "file_path": file_path,
        "custodian": effective_custodian,
        "uploaded_at": now,
        "blockchain_registered": False,
        "blockchain_tx": None,
        "custody_version": 1
    }

    # Persist to MongoDB when available / required
    if db_client.is_connected():
        try:
            doc = {k: v for k, v in record.items() if k != "_id"}
            await db_client.evidence.update_one({"evidence_id": assigned_id}, {"$set": doc}, upsert=True)
        except Exception as e:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            EVIDENCE_STORE.pop(assigned_id, None)
            raise HTTPException(status_code=500, detail=f"Database persistent write failed: {str(e)}")
    elif db_client.require_persistent_storage:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        EVIDENCE_STORE.pop(assigned_id, None)
        raise HTTPException(status_code=503, detail="Persistent database storage is required but unavailable")

    try:
        EVIDENCE_STORE[assigned_id] = record
        from ..services.audit_trail import record_custody_event
        await record_custody_event(
            evidence_id=assigned_id,
            action="EVIDENCE_INGESTION",
            actor_id=effective_custodian,
            case_id=record["case_id"],
            details={
                "file_hash": file_hash,
                "filename": record["filename"],
                "file_size": file_size,
                "previous_custodian": "None",
                "new_custodian": effective_custodian,
                "reason": "Initial digital evidence ingestion"
            },
            custom_timestamp=now
        )
    except Exception as e:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        EVIDENCE_STORE.pop(assigned_id, None)
        if db_client.is_connected():
            try:
                await db_client.evidence.delete_one({"evidence_id": assigned_id})
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Metadata persistence failed: {str(e)}")

    return {
        "status": "success",
        "evidence_id": assigned_id,
        "case_id": record["case_id"],
        "filename": record["filename"],
        "file_hash": file_hash,
        "file_size": file_size,
        "uploaded_at": now
    }

@router.get("", response_model=list[dict])
async def list_evidence(current_user: dict = Depends(get_current_user)):
    """List all ingested evidence records. Allowed roles: All authenticated (Employees receive assigned scope)."""
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")

    user_role = current_user.get("role")
    username = current_user.get("username", "")

    all_evidence = []
    if db_client.is_connected():
        try:
            cursor = db_client.evidence.find({}, {"_id": 0})
            docs = await cursor.to_list(length=1000)
            for d in docs:
                EVIDENCE_STORE[d["evidence_id"]] = d
            all_evidence = docs
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Persistent database read failed: {str(e)}")

    if not all_evidence:
        all_evidence = list(EVIDENCE_STORE.values())

    if user_role == UserRole.EMPLOYEE.value:
        permitted_cases, permitted_evidence = await get_employee_authorized_resources(username)
        return [
            d for d in all_evidence
            if d.get("evidence_id") in permitted_evidence or d.get("case_id") in permitted_cases
        ]

    return all_evidence

@router.get("/{evidence_id}")
async def get_evidence(evidence_id: str, current_user: dict = Depends(get_current_user)):
    """Retrieve evidence record metadata by evidence_id. Allowed roles: All authenticated (Employees require assignment)."""
    user_role = current_user.get("role")
    username = current_user.get("username", "")

    if user_role == UserRole.EMPLOYEE.value:
        permitted_cases, permitted_evidence = await get_employee_authorized_resources(username)
        if evidence_id not in permitted_evidence:
            local_item = EVIDENCE_STORE.get(evidence_id)
            if not local_item or local_item.get("case_id") not in permitted_cases:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: Employee '{username}' is not assigned to evidence '{evidence_id}'."
                )

    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")

    item = None
    if db_client.is_connected():
        try:
            doc = await db_client.evidence.find_one({"evidence_id": evidence_id}, {"_id": 0})
            if doc:
                EVIDENCE_STORE[evidence_id] = doc
                item = doc
            elif db_client.require_persistent_storage:
                raise HTTPException(status_code=404, detail="Evidence not found in persistent store")
        except HTTPException:
            raise
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Persistent database read failed: {str(e)}")

    if not item:
        item = EVIDENCE_STORE.get(evidence_id)

    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")

    return item

@router.get("/download/{filename:path}")
async def download_evidence(filename: str, current_user: dict = Depends(get_current_user)):
    """Download evidence file with path traversal defense. Allowed roles: All authenticated (Employees require assignment)."""
    user_role = current_user.get("role")
    username = current_user.get("username", "")

    # For employees, verify they have permission to access the evidence item that owns this file
    if user_role == UserRole.EMPLOYEE.value:
        permitted_cases, permitted_evidence = await get_employee_authorized_resources(username)
        # Locate corresponding evidence record
        matching_ev = None
        for ev in EVIDENCE_STORE.values():
            if ev.get("filename") == filename or ev.get("stored_filename") == filename or filename in str(ev.get("file_path", "")):
                matching_ev = ev
                break
        if matching_ev:
            if matching_ev.get("evidence_id") not in permitted_evidence and matching_ev.get("case_id") not in permitted_cases:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: Employee '{username}' is not authorized to download file for evidence '{matching_ev.get('evidence_id')}'."
                )

    resolved_path = get_file_path(filename)
    if not resolved_path:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(path=str(resolved_path), filename=resolved_path.name)
