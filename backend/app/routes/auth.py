import os
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel
from ..security.auth import create_access_token, get_current_user
from ..security.permissions import UserRole
from ..security.password import hash_password, verify_password
from ..security.rate_limiter import login_rate_limiter, get_client_ip
from ..services.user_service import get_user, USERS_STORE, strip_sensitive_fields, update_user_profile

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str
    display_name: str
    full_name: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    display_name: str

def _get_credential_hash(env_var: str, default_val: str) -> str:
    """Retrieve password from environment variable if present; fallback to development default."""
    return hash_password(os.getenv(env_var, default_val))

# System user accounts storing cryptographic bcrypt hashes (legacy fallback)
DEMO_USERS = {
    "admin": {
        "password_hash": _get_credential_hash("ADMIN_INITIAL_PASSWORD", "AdminPassword123!"),
        "role": UserRole.ADMIN.value,
        "user_id": "USR-ADMIN-01",
        "is_active": True,
        "full_name": "Senior Administrator",
        "display_name": "Senior Administrator"
    },
    "investigator1": {
        "password_hash": _get_credential_hash("INVESTIGATOR_INITIAL_PASSWORD", "TestPassword123!"),
        "role": UserRole.INVESTIGATOR.value,
        "user_id": "USR-INV-01",
        "is_active": True,
        "full_name": "Lead Forensic Investigator",
        "display_name": "Lead Forensic Investigator"
    },
    "analyst1": {
        "password_hash": _get_credential_hash("ANALYST_INITIAL_PASSWORD", "TestPassword123!"),
        "role": UserRole.ANALYST.value,
        "user_id": "USR-ANA-01",
        "is_active": True,
        "full_name": "Forensic Analyst",
        "display_name": "Forensic Analyst"
    },
    "viewer1": {
        "password_hash": _get_credential_hash("VIEWER_INITIAL_PASSWORD", "TestPassword123!"),
        "role": UserRole.VIEWER.value,
        "user_id": "USR-VIEW-01",
        "is_active": True,
        "full_name": "Compliance Auditor",
        "display_name": "Compliance Auditor"
    },
    "suspended_user": {
        "password_hash": _get_credential_hash("SUSPENDED_INITIAL_PASSWORD", "TestPassword123!"),
        "role": UserRole.VIEWER.value,
        "user_id": "USR-SUSP-01",
        "is_active": False,
        "full_name": "Suspended Reviewer",
        "display_name": "Suspended Reviewer"
    },
    "employee1": {
        "password_hash": _get_credential_hash("EMPLOYEE_INITIAL_PASSWORD", "EmployeePassword123!"),
        "role": UserRole.EMPLOYEE.value,
        "user_id": "USR-EMP-01",
        "is_active": True,
        "full_name": "Digital Evidence Technician",
        "display_name": "Digital Evidence Technician"
    }
}

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    # Safely extract client IP, trusting forwarded headers only from verified proxies
    client_ip = get_client_ip(request)
    ip_key = f"ip:{client_ip}"
    user_key = f"user:{req.username}"

    # Rate limiting: verify neither IP nor username is currently blocked
    login_rate_limiter.check_rate_limit(ip_key)
    login_rate_limiter.check_rate_limit(user_key)

    user = await get_user(req.username)
    if not user:
        user = DEMO_USERS.get(req.username)

    if not user or not verify_password(req.password, user.get("password_hash", "")):
        login_rate_limiter.record_failure(ip_key)
        login_rate_limiter.record_failure(user_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Successful authentication: clear failure history for IP and username
    login_rate_limiter.record_success(ip_key)
    login_rate_limiter.record_success(user_key)

    display_name = user.get("display_name") or user.get("full_name") or user.get("username", req.username)

    token = create_access_token({
        "sub": user["user_id"],
        "username": user.get("username", req.username),
        "role": user["role"],
        "display_name": display_name
    })

    return TokenResponse(
        access_token=token,
        user_id=user["user_id"],
        username=user.get("username", req.username),
        role=user["role"],
        display_name=display_name,
        full_name=display_name
    )

@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """Retrieve full profile metadata for the authenticated user without exposing secrets."""
    username = current_user.get("username")
    user = await get_user(username) if username else None
    if not user:
        user_id = current_user.get("sub")
        if user_id:
            from ..services.user_service import get_user_by_id
            user = await get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authenticated user record not found"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )

    return strip_sensitive_fields(user)

@router.put("/profile", status_code=status.HTTP_200_OK)
async def update_profile(req: ProfileUpdateRequest, current_user: dict = Depends(get_current_user)):
    """Update display name for the currently authenticated user."""
    username = current_user.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username missing from token")
    try:
        updated = await update_user_profile(username, req.display_name)
        return updated
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: dict = Depends(get_current_user)):
    """Terminate current user session. Allowed roles: All authenticated."""
    return {"status": "success", "message": "Successfully logged out"}

@router.get("/bootstrap", status_code=status.HTTP_200_OK)
async def get_bootstrap_status():
    """Verify bootstrap administrator initialization without exposing credentials. Public."""
    admin = await get_user("admin") or DEMO_USERS.get("admin")
    sa_username = os.getenv("SUPER_ADMIN_INITIAL_USERNAME", "superadmin").strip()
    sa = await get_user(sa_username)
    return {
        "status": "initialized",
        "bootstrap_admin": "admin",
        "role": admin["role"] if admin else None,
        "is_active": admin.get("is_active", False) if admin else False,
        "super_admin_bootstrapped": sa is not None,
        "super_admin_active": sa.get("is_active", False) if sa else False
    }
