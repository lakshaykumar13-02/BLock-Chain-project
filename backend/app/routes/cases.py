from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
import datetime

from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..database.mongodb import db_client
from ..services.task_service import get_employee_authorized_resources

router = APIRouter(prefix="/cases", tags=["Cases"])

class CaseCreate(BaseModel):
    case_number: str | None = None
    case_id: str | None = None
    title: str
    description: str = ""

class CaseResponse(BaseModel):
    case_id: str
    case_number: str = ""
    title: str
    description: str = ""
    created_at: str = ""
    is_deleted: bool = False


# Memory storage store for reliable testing & development fallback
CASES_STORE: dict[str, dict] = {}

@router.post("", status_code=status.HTTP_201_CREATED, response_model=CaseResponse)
async def create_case(
    req: CaseCreate,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """Create a new case. Allowed roles: ADMIN, INVESTIGATOR."""
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent database storage is required but currently unavailable"
        )

    assigned_case_id = req.case_id or f"CASE-{len(CASES_STORE) + 1:04d}"
    assigned_case_number = req.case_number or assigned_case_id
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "case_id": assigned_case_id,
        "case_number": assigned_case_number,
        "title": req.title,
        "description": req.description,
        "created_at": now,
        "is_deleted": False
    }

    if db_client.is_connected():
        try:
            doc = {k: v for k, v in record.items() if k != "_id"}
            await db_client.cases.update_one({"case_id": assigned_case_id}, {"$set": doc}, upsert=True)
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=500, detail=f"Database persistent write failed: {str(e)}")
    elif db_client.require_persistent_storage:
        raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")

    CASES_STORE[assigned_case_id] = record
    return CaseResponse(**record)

@router.get("", response_model=list[CaseResponse])
async def list_cases(current_user: dict = Depends(get_current_user)):
    """List all active cases (excluding soft-deleted). Allowed roles: All authenticated (Employees receive assigned scope)."""
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")

    user_role = current_user.get("role")
    username = current_user.get("username", "")

    all_cases = []
    if db_client.is_connected():
        try:
            cursor = db_client.cases.find({"is_deleted": {"$ne": True}}, {"_id": 0})
            cases = await cursor.to_list(length=1000)
            for c in cases:
                CASES_STORE[c["case_id"]] = c
            all_cases = [CaseResponse(**c) for c in cases]
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Persistent database read failed: {str(e)}")

    if not all_cases:
        all_cases = [CaseResponse(**c) for c in CASES_STORE.values() if not c.get("is_deleted")]

    if user_role == UserRole.EMPLOYEE.value:
        permitted_cases, _ = await get_employee_authorized_resources(username)
        return [c for c in all_cases if c.case_id in permitted_cases]

    return all_cases

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str, current_user: dict = Depends(get_current_user)):
    """Retrieve case by case_id. Allowed roles: All authenticated (Employees require assignment)."""
    user_role = current_user.get("role")
    username = current_user.get("username", "")

    if user_role == UserRole.EMPLOYEE.value:
        permitted_cases, _ = await get_employee_authorized_resources(username)
        if case_id not in permitted_cases:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Employee '{username}' is not assigned to case '{case_id}'."
            )

    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")

    if db_client.is_connected():
        try:
            case = await db_client.cases.find_one({"case_id": case_id}, {"_id": 0})
            if case and not case.get("is_deleted"):
                CASES_STORE[case_id] = case
                return CaseResponse(**case)
            if case and case.get("is_deleted"):
                raise HTTPException(status_code=404, detail="Case not found")
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=404, detail="Case not found")
        except HTTPException:
            raise
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=503, detail=f"Persistent database read failed: {str(e)}")

    case = CASES_STORE.get(case_id)
    if not case or case.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseResponse(**case)

@router.delete("/{case_id}", status_code=status.HTTP_200_OK)
async def soft_delete_case(
    case_id: str,
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """Soft delete case by marking is_deleted=True. Allowed roles: ADMIN only."""
    if db_client.require_persistent_storage and not db_client.is_connected():
        raise HTTPException(status_code=503, detail="Persistent database storage is unavailable")
    if db_client.is_connected():
        try:
            res = await db_client.cases.update_one({"case_id": case_id}, {"$set": {"is_deleted": True}})
            if res.matched_count == 0 and db_client.require_persistent_storage:
                raise HTTPException(status_code=404, detail="Case not found")
        except HTTPException:
            raise
        except Exception as e:
            if db_client.require_persistent_storage:
                raise HTTPException(status_code=500, detail=f"Failed to soft delete case: {e}")

    case = CASES_STORE.get(case_id)
    if not case or case.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Case not found")
    case["is_deleted"] = True
    return {"status": "success", "message": f"Case {case_id} soft-deleted"}
