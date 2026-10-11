from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
import datetime

router = APIRouter(prefix="/cases", tags=["Cases"])

class CaseCreate(BaseModel):
    case_number: str | None = None
    case_id: str | None = None
    title: str
    description: str = ""

class CaseResponse(BaseModel):
    case_id: str
    case_number: str
    title: str
    description: str
    created_at: str
    is_deleted: bool = False

# Memory storage store for reliable testing & development fallback
CASES_STORE: dict[str, dict] = {}

@router.post("", status_code=status.HTTP_201_CREATED, response_model=CaseResponse)
async def create_case(req: CaseCreate):
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
    CASES_STORE[assigned_case_id] = record
    return CaseResponse(**record)

@router.get("", response_model=list[CaseResponse])
async def list_cases():
    """List all active cases (excluding soft-deleted)."""
    return [CaseResponse(**c) for c in CASES_STORE.values() if not c.get("is_deleted")]

@router.get("/{case_id}", response_model=CaseResponse)
async def get_case(case_id: str):
    case = CASES_STORE.get(case_id)
    if not case or case.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Case not found")
    return CaseResponse(**case)

@router.delete("/{case_id}", status_code=status.HTTP_200_OK)
async def soft_delete_case(case_id: str):
    """Soft delete case by marking is_deleted=True."""
    case = CASES_STORE.get(case_id)
    if not case or case.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Case not found")
    case["is_deleted"] = True
    return {"status": "success", "message": f"Case {case_id} soft-deleted"}
