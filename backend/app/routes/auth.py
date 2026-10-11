from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from ..security.auth import create_access_token
from ..security.permissions import UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str

# Default system users for development and testing
DEMO_USERS = {
    "admin": {
        "password": "AdminPassword123!",
        "role": UserRole.ADMIN.value,
        "user_id": "USR-ADMIN-01"
    },
    "investigator1": {
        "password": "TestPassword123!",
        "role": UserRole.INVESTIGATOR.value,
        "user_id": "USR-INV-01"
    },
    "analyst1": {
        "password": "TestPassword123!",
        "role": UserRole.ANALYST.value,
        "user_id": "USR-ANA-01"
    },
    "viewer1": {
        "password": "TestPassword123!",
        "role": UserRole.VIEWER.value,
        "user_id": "USR-VIEW-01"
    }
}

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = DEMO_USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
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
