from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from ..security.auth import create_access_token, get_current_user
from ..security.permissions import UserRole
from ..security.password import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str

# System user accounts storing cryptographic bcrypt hashes rather than plaintext passwords
DEMO_USERS = {
    "admin": {
        "password_hash": hash_password("AdminPassword123!"),
        "role": UserRole.ADMIN.value,
        "user_id": "USR-ADMIN-01",
        "is_active": True
    },
    "investigator1": {
        "password_hash": hash_password("TestPassword123!"),
        "role": UserRole.INVESTIGATOR.value,
        "user_id": "USR-INV-01",
        "is_active": True
    },
    "analyst1": {
        "password_hash": hash_password("TestPassword123!"),
        "role": UserRole.ANALYST.value,
        "user_id": "USR-ANA-01",
        "is_active": True
    },
    "viewer1": {
        "password_hash": hash_password("TestPassword123!"),
        "role": UserRole.VIEWER.value,
        "user_id": "USR-VIEW-01",
        "is_active": True
    },
    "suspended_user": {
        "password_hash": hash_password("TestPassword123!"),
        "role": UserRole.VIEWER.value,
        "user_id": "USR-SUSP-01",
        "is_active": False
    }
}

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = DEMO_USERS.get(req.username)
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    token = create_access_token({
        "sub": user["user_id"],
        "username": req.username,
        "role": user["role"]
    })

    return TokenResponse(
        access_token=token,
        user_id=user["user_id"],
        role=user["role"]
    )

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: dict = Depends(get_current_user)):
    """Terminate current user session. Allowed roles: All authenticated."""
    return {"status": "success", "message": "Successfully logged out"}

@router.get("/bootstrap", status_code=status.HTTP_200_OK)
async def get_bootstrap_status():
    """Verify bootstrap administrator initialization without exposing credentials. Public."""
    admin = DEMO_USERS.get("admin")
    return {
        "status": "initialized",
        "bootstrap_admin": "admin",
        "role": admin["role"] if admin else None,
        "is_active": admin.get("is_active", False) if admin else False
    }
