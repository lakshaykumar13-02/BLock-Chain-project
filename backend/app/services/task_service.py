import datetime
import uuid
import logging
from typing import Optional, List, Dict, Any, Tuple
from ..security.permissions import UserRole
from ..database.mongodb import db_client
from .user_service import record_account_audit_event, get_user

logger = logging.getLogger(__name__)

TASKS_STORE: Dict[str, dict] = {}

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def _sync_init_base_tasks() -> None:
    """Seed initial demonstration task for employee1 on system initialization."""
    demo_task_id = "TSK-2026-0001"
    if demo_task_id not in TASKS_STORE:
        now = _now_iso()
        task = {
            "task_id": demo_task_id,
            "title": "Forensic Evidence Integrity Verification",
            "description": "Perform SHA-256 byte recalculation and verify against on-chain blockchain ledger for EV-001.",
            "case_id": "CV-2026-001",
            "permitted_evidence_ids": ["EV-001"],
            "assigned_to_username": "employee1",
            "assigned_to_user_id": "USR-EMP-01",
            "assigned_by_username": "admin",
            "assigned_by_user_id": "USR-ADMIN-01",
            "status": "ASSIGNED",
            "progress_percent": 25,
            "priority": "HIGH",
            "due_date": "2026-11-15T18:00:00Z",
            "created_at": now,
            "updated_at": now,
            "activity_log": [
                {
                    "timestamp": now,
                    "actor": "admin",
                    "action": "TASK_CREATED",
                    "status": "ASSIGNED",
                    "progress_percent": 0,
                    "note": "Initial task dispatch: verify evidence integrity on Case CV-2026-001."
                },
                {
                    "timestamp": now,
                    "actor": "employee1",
                    "action": "PROGRESS_UPDATED",
                    "status": "IN_PROGRESS",
                    "progress_percent": 25,
                    "note": "Initial evidence digest inspected; awaiting cryptographic ledger comparison."
                }
            ]
        }
        TASKS_STORE[demo_task_id] = task

_sync_init_base_tasks()

async def create_task(
    actor_id: str,
    actor_username: str,
    title: str,
    description: str,
    case_id: str,
    permitted_evidence_ids: List[str],
    assigned_to_username: str,
    priority: str = "MEDIUM",
    due_date: Optional[str] = None
) -> dict:
    """Create a new task and assign to an employee. Only callable by ADMIN or INVESTIGATOR."""
    title = title.strip()
    if not title or len(title) < 3 or len(title) > 120:
        raise ValueError("Task title must be between 3 and 120 characters.")

    assigned_to_username = assigned_to_username.strip()
    target_user = await get_user(assigned_to_username)
    if not target_user:
        raise KeyError(f"Assignee user '{assigned_to_username}' not found.")
    if target_user.get("role") != UserRole.EMPLOYEE.value:
        raise ValueError(f"Tasks can only be assigned to accounts with role 'EMPLOYEE' (target has '{target_user.get('role')}').")

    clean_evidence_ids = [e.strip() for e in permitted_evidence_ids if e and e.strip()]
    task_id = f"TSK-{uuid.uuid4().hex[:8].upper()}"
    now = _now_iso()

    task_record = {
        "task_id": task_id,
        "title": title,
        "description": description.strip() if description else "",
        "case_id": case_id.strip(),
        "permitted_evidence_ids": clean_evidence_ids,
        "assigned_to_username": assigned_to_username,
        "assigned_to_user_id": target_user.get("user_id", "UNKNOWN"),
        "assigned_by_username": actor_username,
        "assigned_by_user_id": actor_id,
        "status": "ASSIGNED",
        "progress_percent": 0,
        "priority": priority.upper() if priority and priority.upper() in ("LOW", "MEDIUM", "HIGH", "CRITICAL") else "MEDIUM",
        "due_date": due_date,
        "created_at": now,
        "updated_at": now,
        "activity_log": [
            {
                "timestamp": now,
                "actor": actor_username,
                "action": "TASK_CREATED",
                "status": "ASSIGNED",
                "progress_percent": 0,
                "note": f"Task created and assigned to {assigned_to_username}."
            }
        ]
    }

    TASKS_STORE[task_id] = task_record

    if db_client.is_connected() and hasattr(db_client, "tasks"):
        try:
            await db_client.tasks.insert_one(task_record.copy())
        except Exception as e:
            logger.warning(f"Could not persist task to DB: {e}")

    record_account_audit_event(
        action="TASK_ASSIGNED",
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=target_user.get("user_id", "UNKNOWN"),
        target_username=assigned_to_username,
        outcome="SUCCESS",
        details={
            "task_id": task_id,
            "case_id": case_id,
            "permitted_evidence_count": len(clean_evidence_ids)
        }
    )

    return task_record


async def list_tasks(
    caller_role: str,
    caller_username: str,
    case_id: Optional[str] = None
) -> List[dict]:
    """
    List tasks. Employees receive strictly their own assigned tasks.
    Admins and Investigators can view all tasks or filter by case.
    """
    _sync_init_base_tasks()
    all_tasks = list(TASKS_STORE.values())

    if db_client.is_connected() and hasattr(db_client, "tasks"):
        try:
            query = {}
            if caller_role == UserRole.EMPLOYEE.value:
                query["assigned_to_username"] = caller_username
            elif case_id:
                query["case_id"] = case_id
            cursor = db_client.tasks.find(query, {"_id": 0})
            docs = await cursor.to_list(length=500) if hasattr(cursor, "to_list") else []
            for doc in docs:
                TASKS_STORE[doc["task_id"]] = doc
            if docs:
                all_tasks = docs
        except Exception:
            pass

    if caller_role == UserRole.EMPLOYEE.value:
        filtered = [t for t in all_tasks if t.get("assigned_to_username") == caller_username]
    else:
        filtered = all_tasks
        if case_id:
            filtered = [t for t in filtered if t.get("case_id") == case_id]

    return sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True)


async def get_task(
    task_id: str,
    caller_role: str,
    caller_username: str
) -> Optional[dict]:
    """Retrieve specific task details, enforcing employee isolation."""
    task = TASKS_STORE.get(task_id)

    if not task and db_client.is_connected() and hasattr(db_client, "tasks"):
        try:
            doc = await db_client.tasks.find_one({"task_id": task_id}, {"_id": 0})
            if doc:
                TASKS_STORE[task_id] = doc
                task = doc
        except Exception:
            pass

    if not task:
        return None

    if caller_role == UserRole.EMPLOYEE.value and task.get("assigned_to_username") != caller_username:
        raise PermissionError(f"Employee '{caller_username}' lacks permission to view task '{task_id}'.")

    return task


async def update_task_progress(
    task_id: str,
    actor_username: str,
    actor_role: str,
    status: Optional[str] = None,
    progress_percent: Optional[int] = None,
    note: Optional[str] = None
) -> dict:
    """
    Update status, progress percent, and append progress notes to a task.
    Allowed for assigned employee, ADMIN, or INVESTIGATOR.
    """
    task = await get_task(task_id, caller_role=actor_role, caller_username=actor_username)
    if not task:
        raise KeyError(f"Task '{task_id}' not found.")

    if actor_role == UserRole.EMPLOYEE.value and task.get("assigned_to_username") != actor_username:
        raise PermissionError("Employees can only update progress on their own assigned tasks.")

    now = _now_iso()
    updated = False

    if status is not None:
        valid_statuses = ("ASSIGNED", "IN_PROGRESS", "COMPLETED", "BLOCKED")
        norm_status = status.strip().upper()
        if norm_status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}.")
        task["status"] = norm_status
        updated = True

    if progress_percent is not None:
        if not (0 <= progress_percent <= 100):
            raise ValueError("progress_percent must be an integer between 0 and 100.")
        task["progress_percent"] = progress_percent
        if progress_percent == 100:
            task["status"] = "COMPLETED"
        updated = True

    effective_note = note.strip() if note and note.strip() else f"Progress updated to {task.get('progress_percent', 0)}% ({task.get('status', 'IN_PROGRESS')})"
    activity_entry = {
        "timestamp": now,
        "actor": actor_username,
        "action": "PROGRESS_UPDATED",
        "status": task.get("status"),
        "progress_percent": task.get("progress_percent"),
        "note": effective_note
    }

    if "activity_log" not in task:
        task["activity_log"] = []
    task["activity_log"].append(activity_entry)
    task["updated_at"] = now
    TASKS_STORE[task_id] = task

    if db_client.is_connected() and hasattr(db_client, "tasks"):
        try:
            await db_client.tasks.update_one(
                {"task_id": task_id},
                {"$set": {
                    "status": task["status"],
                    "progress_percent": task["progress_percent"],
                    "updated_at": now,
                    "activity_log": task["activity_log"]
                }}
            )
        except Exception as e:
            logger.warning(f"Could not persist task progress update to DB: {e}")

    record_account_audit_event(
        action="TASK_PROGRESS_UPDATED",
        actor_id=actor_username,
        actor_username=actor_username,
        target_account_id=task.get("assigned_to_user_id", "UNKNOWN"),
        target_username=task.get("assigned_to_username", "UNKNOWN"),
        outcome="SUCCESS",
        details={
            "task_id": task_id,
            "status": task["status"],
            "progress_percent": task["progress_percent"],
            "note": effective_note
        }
    )

    return task


async def get_employee_authorized_resources(username: str) -> Tuple[set, set]:
    """Return sets of (case_ids, evidence_ids) permitted for an employee via active task assignments."""
    _sync_init_base_tasks()
    permitted_cases = set()
    permitted_evidence = set()

    for task in TASKS_STORE.values():
        if task.get("assigned_to_username") == username:
            cid = task.get("case_id")
            if cid:
                permitted_cases.add(cid)
            for eid in task.get("permitted_evidence_ids", []):
                if eid:
                    permitted_evidence.add(eid)

    if db_client.is_connected() and hasattr(db_client, "tasks"):
        try:
            cursor = db_client.tasks.find({"assigned_to_username": username}, {"_id": 0, "case_id": 1, "permitted_evidence_ids": 1})
            docs = await cursor.to_list(length=200) if hasattr(cursor, "to_list") else []
            for doc in docs:
                cid = doc.get("case_id")
                if cid:
                    permitted_cases.add(cid)
                for eid in doc.get("permitted_evidence_ids", []):
                    if eid:
                        permitted_evidence.add(eid)
        except Exception:
            pass

    return permitted_cases, permitted_evidence
