from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional

from ..security.permissions import require_role, UserRole
from ..services.user_service import (
    list_employees,
    create_employee,
    set_employee_status,
    reset_employee_password,
    remove_employee
)

router = APIRouter(prefix="/admin/employees", tags=["Admin Employee Management"])

class CreateEmployeeRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None

class UpdateEmployeeStatusRequest(BaseModel):
    is_active: bool

class ResetEmployeePasswordRequest(BaseModel):
    new_password: str

class RemoveEmployeeRequest(BaseModel):
    confirm: bool

@router.get("", status_code=status.HTTP_200_OK)
async def get_employee_accounts(
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """List all Employee accounts with metadata (never returns password hashes). Only callable by ADMIN."""
    return await list_employees()

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_employee_account(
    req: CreateEmployeeRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """Provision a new Employee account. Only callable by ADMIN."""
    actor_id = current_user.get("sub", current_user.get("username", "admin"))
    actor_username = current_user.get("username", "admin")

    try:
        effective_name = req.display_name or req.full_name
        created = await create_employee(
            actor_id=actor_id,
            actor_username=actor_username,
            username=req.username,
            password=req.password,
            full_name=effective_name
        )
        return created
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.put("/{username}/status", status_code=status.HTTP_200_OK)
async def update_employee_status_endpoint(
    username: str,
    req: UpdateEmployeeStatusRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """Activate, deactivate, or reactivate an Employee account. Only callable by ADMIN."""
    actor_id = current_user.get("sub", current_user.get("username", "admin"))
    actor_username = current_user.get("username", "admin")

    try:
        updated = await set_employee_status(
            actor_id=actor_id,
            actor_username=actor_username,
            target_username=username,
            is_active=req.is_active
        )
        return updated
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/{username}/reset-password", status_code=status.HTTP_200_OK)
async def reset_employee_password_endpoint(
    username: str,
    req: ResetEmployeePasswordRequest,
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """Reset an Employee account's access credentials and immediately invalidate all prior sessions."""
    actor_id = current_user.get("sub", current_user.get("username", "admin"))
    actor_username = current_user.get("username", "admin")

    try:
        updated = await reset_employee_password(
            actor_id=actor_id,
            actor_username=actor_username,
            target_username=username,
            new_password=req.new_password
        )
        return {
            "status": "success",
            "message": f"Credentials for Employee '{username}' have been reset and existing sessions revoked.",
            "account": updated
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/{username}", status_code=status.HTTP_200_OK)
async def remove_employee_account(
    username: str,
    req: Optional[RemoveEmployeeRequest] = None,
    confirm: bool = Query(False, description="Explicit confirmation parameter"),
    current_user: dict = Depends(require_role([UserRole.ADMIN]))
):
    """Safely remove an Employee account. Requires explicit confirmation (confirm=True)."""
    actor_id = current_user.get("sub", current_user.get("username", "admin"))
    actor_username = current_user.get("username", "admin")

    confirmation = confirm or (req and req.confirm)
    if not confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit confirmation (confirm=true) is required to remove an employee account."
        )

    try:
        result = await remove_employee(
            actor_id=actor_id,
            actor_username=actor_username,
            target_username=username,
            confirmation=True
        )
        return result
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
