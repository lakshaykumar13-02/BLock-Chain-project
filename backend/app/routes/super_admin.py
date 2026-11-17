from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional

from ..security.permissions import require_role, UserRole
from ..services.user_service import (
    list_admins,
    get_platform_summary,
    create_admin,
    set_admin_status,
    reset_admin_password,
    remove_admin,
    get_account_audit_logs
)

router = APIRouter(prefix="/superadmin", tags=["Super Admin Platform Governance"])

class CreateAdminRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None

class UpdateAdminStatusRequest(BaseModel):
    is_active: bool

class ResetAdminPasswordRequest(BaseModel):
    new_password: str

class RemoveAdminRequest(BaseModel):
    confirm: bool

@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_summary(
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Platform-level administrator and governance summary for Super Admin dashboard."""
    return await get_platform_summary()

@router.get("/admins", status_code=status.HTTP_200_OK)
async def get_admin_accounts(
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """List all Admin accounts with metadata (never returns password hashes)."""
    return await list_admins()

@router.post("/admins", status_code=status.HTTP_201_CREATED)
async def create_admin_account(
    req: CreateAdminRequest,
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Provision a new Admin account. Only callable by SUPER_ADMIN."""
    actor_id = current_user.get("sub", "SUPER_ADMIN")
    actor_username = current_user.get("username", "superadmin")

    try:
        effective_name = req.display_name or req.full_name
        created = await create_admin(
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

@router.put("/admins/{username}/status", status_code=status.HTTP_200_OK)
async def update_admin_status_endpoint(
    username: str,
    req: UpdateAdminStatusRequest,
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Activate, deactivate, or reactivate an Admin account. Enforces anti-lockout rules."""
    actor_id = current_user.get("sub", "SUPER_ADMIN")
    actor_username = current_user.get("username", "superadmin")

    try:
        updated = await set_admin_status(
            actor_id=actor_id,
            actor_username=actor_username,
            target_username=username,
            is_active=req.is_active
        )
        return updated
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/admins/{username}/reset-password", status_code=status.HTTP_200_OK)
async def reset_admin_password_endpoint(
    username: str,
    req: ResetAdminPasswordRequest,
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Reset an Admin account's access credentials and immediately invalidate all prior sessions."""
    actor_id = current_user.get("sub", "SUPER_ADMIN")
    actor_username = current_user.get("username", "superadmin")

    try:
        updated = await reset_admin_password(
            actor_id=actor_id,
            actor_username=actor_username,
            target_username=username,
            new_password=req.new_password
        )
        return {
            "status": "success",
            "message": f"Credentials for Admin '{username}' have been reset and existing sessions revoked.",
            "account": updated
        }
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.delete("/admins/{username}", status_code=status.HTTP_200_OK)
async def remove_admin_account(
    username: str,
    req: Optional[RemoveAdminRequest] = None,
    confirm: bool = Query(False, description="Explicit confirmation parameter"),
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """Safely remove an Admin account. Requires explicit confirmation (confirm=True)."""
    actor_id = current_user.get("sub", "SUPER_ADMIN")
    actor_username = current_user.get("username", "superadmin")

    confirmation = confirm or (req and req.confirm)
    if not confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit confirmation (confirm=true) is required to remove an administrator account."
        )

    try:
        result = await remove_admin(
            actor_id=actor_id,
            actor_username=actor_username,
            target_username=username,
            confirmation=True
        )
        return result
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/audit-logs", status_code=status.HTTP_200_OK)
async def get_account_management_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    """View platform-level account-management audit trail (Admin lifecycle events)."""
    return get_account_audit_logs(limit=limit)
