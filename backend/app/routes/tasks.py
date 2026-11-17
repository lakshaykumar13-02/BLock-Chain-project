from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List

from ..security.auth import get_current_user
from ..security.permissions import require_role, UserRole
from ..services.task_service import (
    create_task,
    list_tasks,
    get_task,
    update_task_progress
)

router = APIRouter(prefix="/tasks", tags=["Task Management & Workflows"])

class CreateTaskRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    case_id: str
    permitted_evidence_ids: Optional[List[str]] = []
    assigned_to_username: str
    priority: Optional[str] = "MEDIUM"
    due_date: Optional[str] = None

class UpdateTaskProgressRequest(BaseModel):
    status: Optional[str] = None
    progress_percent: Optional[int] = None
    note: Optional[str] = None

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_new_task(
    req: CreateTaskRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN, UserRole.INVESTIGATOR]))
):
    """Dispatch and assign a new task to an Employee. Allowed roles: ADMIN, INVESTIGATOR."""
    actor_id = current_user.get("sub", current_user.get("username", "admin"))
    actor_username = current_user.get("username", "admin")

    try:
        task = await create_task(
            actor_id=actor_id,
            actor_username=actor_username,
            title=req.title,
            description=req.description or "",
            case_id=req.case_id,
            permitted_evidence_ids=req.permitted_evidence_ids or [],
            assigned_to_username=req.assigned_to_username,
            priority=req.priority or "MEDIUM",
            due_date=req.due_date
        )
        return task
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("", status_code=status.HTTP_200_OK)
async def get_tasks(
    case_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    List tasks. Employees receive strictly their own assigned tasks.
    Admins and Investigators can view all tasks or filter by case.
    """
    role = current_user.get("role", UserRole.VIEWER.value)
    username = current_user.get("username", "")
    return await list_tasks(caller_role=role, caller_username=username, case_id=case_id)


@router.get("/my-tasks", status_code=status.HTTP_200_OK)
async def get_my_tasks(
    current_user: dict = Depends(require_role([UserRole.EMPLOYEE]))
):
    """Convenience endpoint returning assigned tasks for the currently authenticated Employee."""
    username = current_user.get("username", "")
    return await list_tasks(caller_role=UserRole.EMPLOYEE.value, caller_username=username)


@router.get("/{task_id}", status_code=status.HTTP_200_OK)
async def get_task_by_id(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve details for a specific task. Enforces employee assignment isolation."""
    role = current_user.get("role", UserRole.VIEWER.value)
    username = current_user.get("username", "")

    try:
        task = await get_task(task_id, caller_role=role, caller_username=username)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found.")
        return task
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.put("/{task_id}/progress", status_code=status.HTTP_200_OK)
async def update_task_progress_endpoint(
    task_id: str,
    req: UpdateTaskProgressRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Update progress, status, and activity notes on a task.
    Allowed for assigned Employee, ADMIN, or INVESTIGATOR.
    """
    role = current_user.get("role", UserRole.VIEWER.value)
    username = current_user.get("username", "")

    # Role restriction: Only EMPLOYEE (own task), ADMIN, or INVESTIGATOR can update task progress
    if role not in (UserRole.EMPLOYEE.value, UserRole.ADMIN.value, UserRole.INVESTIGATOR.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' is not authorized to update task progress."
        )

    try:
        updated_task = await update_task_progress(
            task_id=task_id,
            actor_username=username,
            actor_role=role,
            status=req.status,
            progress_percent=req.progress_percent,
            note=req.note
        )
        return updated_task
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
