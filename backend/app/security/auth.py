import os
import datetime
import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security_scheme = HTTPBearer(auto_error=False)

DEFAULT_JWT_SECRET = "chainvault_default_secret_key_change_in_production"
KNOWN_PLACEHOLDER_SECRETS = {
    DEFAULT_JWT_SECRET,
    "replace_with_cryptographically_secure_random_key_min_32_chars",
    "secret",
    "changeme",
    "password",
    "admin"
}
JWT_SECRET = os.getenv("JWT_SECRET", DEFAULT_JWT_SECRET)
if os.getenv("ENVIRONMENT", "development").lower() == "production":
    if JWT_SECRET in KNOWN_PLACEHOLDER_SECRETS or len(JWT_SECRET) < 32:
        raise RuntimeError("CRITICAL SECURITY ERROR: Running in production with a default, placeholder, or short (<32 chars) JWT_SECRET is strictly prohibited! Set a cryptographically secure JWT_SECRET.")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

REVOKED_USERS_BEFORE: dict[str, float] = {}
DEACTIVATED_USERS: set[str] = set()

def revoke_user_sessions(username: str) -> None:
    """Invalidate all tokens issued before now for the specified user."""
    import time
    REVOKED_USERS_BEFORE[username] = time.time()

def deactivate_user_session(username: str) -> None:
    """Mark user as deactivated, rejecting all tokens."""
    DEACTIVATED_USERS.add(username)
    revoke_user_sessions(username)

def reactivate_user_session(username: str) -> None:
    """Allow user to authenticate again."""
    DEACTIVATED_USERS.discard(username)

def is_user_session_revoked(username: str, iat: float | None) -> bool:
    """Check if token is revoked or user is deactivated."""
    if username in DEACTIVATED_USERS:
        return True
    revoked_before = REVOKED_USERS_BEFORE.get(username)
    if revoked_before is not None:
        if iat is None or iat <= revoked_before:
            return True
    return False

def create_access_token(data: dict, expires_delta: datetime.timedelta = None) -> str:
    """Generate a signed JWT token with issued-at (iat) timestamp."""
    to_encode = data.copy()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + datetime.timedelta(minutes=JWT_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now_utc.timestamp()})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT token, ensuring active session status."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username = payload.get("username")
        iat = payload.get("iat")
        if username and is_user_session_revoked(username, iat):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked or account is deactivated"
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security_scheme)) -> dict:
    """Dependency to retrieve and validate the current authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return decode_access_token(credentials.credentials)
