from enum import Enum
from fastapi import Depends, HTTPException, status
from .auth import get_current_user

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INVESTIGATOR = "INVESTIGATOR"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"

def require_role(allowed_roles: list[UserRole]):
    """FastAPI dependency to verify the caller has one of the allowed roles."""
    def role_checker(current_user: dict = Depends(get_current_user)):
        user_role = current_user.get("role", UserRole.VIEWER.value)
        allowed_values = [r.value if isinstance(r, UserRole) else r for r in allowed_roles]
        if user_role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' lacks permission for this action"
            )
        return current_user
    return role_checker
