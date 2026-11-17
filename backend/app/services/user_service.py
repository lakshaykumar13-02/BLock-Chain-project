import os
import uuid
import logging
import datetime
import asyncio
from typing import Optional

from ..security.permissions import UserRole
from ..security.password import hash_password, verify_password
from ..security.auth import revoke_user_sessions, deactivate_user_session, reactivate_user_session
from ..database.mongodb import db_client

logger = logging.getLogger(__name__)

# Synchronized in-memory user registry for instant lookups and offline fallback
USERS_STORE: dict[str, dict] = {}
ACCOUNT_AUDIT_LOGS: list[dict] = []

def _get_env_password_hash(env_var: str, default_val: str) -> str:
    return hash_password(os.getenv(env_var, default_val))

def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def record_account_audit_event(
    action: str,
    actor_id: str,
    actor_username: str,
    target_account_id: str,
    target_username: str,
    outcome: str = "SUCCESS",
    details: Optional[dict] = None
) -> dict:
    """
    Record an immutable account-management audit event.
    NEVER includes passwords, credential hashes, or secret tokens.
    """
    event = {
        "event_id": f"AUD-ACCT-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": _now_iso(),
        "category": "ACCOUNT_MANAGEMENT",
        "action": action,
        "actor_id": actor_id,
        "actor_username": actor_username,
        "target_account_id": target_account_id,
        "target_username": target_username,
        "outcome": outcome,
        "details": details or {}
    }
    ACCOUNT_AUDIT_LOGS.insert(0, event)
    # Attempt async DB write in background without failing if offline
    try:
        if db_client.is_connected() and hasattr(db_client, "audit_logs"):
            # Schedule or fire task if loop is active
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(db_client.audit_logs.insert_one(event.copy()))
            except RuntimeError:
                pass
    except Exception as e:
        logger.warning(f"Could not persist account audit event to database: {e}")
    return event

_user_lock = asyncio.Lock()

def _sync_init_base_users() -> None:
    """Eager synchronous initialization of base demo users and environment-configured Super Admin."""
    base_users = [
        {
            "username": "admin",
            "password_hash": _get_env_password_hash("ADMIN_INITIAL_PASSWORD", "AdminPassword123!"),
            "role": UserRole.ADMIN.value,
            "user_id": "USR-ADMIN-01",
            "is_active": True,
            "full_name": "Senior Administrator",
            "display_name": "Senior Administrator",
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        },
        {
            "username": "investigator1",
            "password_hash": _get_env_password_hash("INVESTIGATOR_INITIAL_PASSWORD", "TestPassword123!"),
            "role": UserRole.INVESTIGATOR.value,
            "user_id": "USR-INV-01",
            "is_active": True,
            "full_name": "Lead Forensic Investigator",
            "display_name": "Lead Forensic Investigator",
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        },
        {
            "username": "analyst1",
            "password_hash": _get_env_password_hash("ANALYST_INITIAL_PASSWORD", "TestPassword123!"),
            "role": UserRole.ANALYST.value,
            "user_id": "USR-ANA-01",
            "is_active": True,
            "full_name": "Forensic Analyst",
            "display_name": "Forensic Analyst",
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        },
        {
            "username": "viewer1",
            "password_hash": _get_env_password_hash("VIEWER_INITIAL_PASSWORD", "TestPassword123!"),
            "role": UserRole.VIEWER.value,
            "user_id": "USR-VIEW-01",
            "is_active": True,
            "full_name": "Compliance Auditor",
            "display_name": "Compliance Auditor",
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        },
        {
            "username": "suspended_user",
            "password_hash": _get_env_password_hash("SUSPENDED_INITIAL_PASSWORD", "TestPassword123!"),
            "role": UserRole.VIEWER.value,
            "user_id": "USR-SUSP-01",
            "is_active": False,
            "full_name": "Suspended Reviewer",
            "display_name": "Suspended Reviewer",
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        },
        {
            "username": "employee1",
            "password_hash": _get_env_password_hash("EMPLOYEE_INITIAL_PASSWORD", "EmployeePassword123!"),
            "role": UserRole.EMPLOYEE.value,
            "user_id": "USR-EMP-01",
            "is_active": True,
            "full_name": "Digital Evidence Technician",
            "display_name": "Digital Evidence Technician",
            "created_at": _now_iso(),
            "updated_at": _now_iso()
        }
    ]
    for u in base_users:
        if u["username"] not in USERS_STORE:
            USERS_STORE[u["username"]] = u
            if not u["is_active"]:
                deactivate_user_session(u["username"])

    sa_username = os.getenv("SUPER_ADMIN_INITIAL_USERNAME", "superadmin").strip()
    default_dev_pwd = "SuperAdminDev2026!" if os.getenv("ENVIRONMENT", "development").lower() != "production" else ""
    sa_password = os.getenv("SUPER_ADMIN_INITIAL_PASSWORD", default_dev_pwd)
    if sa_password and sa_username not in USERS_STORE:
        sa_user = {
            "user_id": "USR-SUPERADMIN-01",
            "username": sa_username,
            "password_hash": hash_password(sa_password),
            "role": UserRole.SUPER_ADMIN.value,
            "is_active": True,
            "full_name": "Platform Owner",
            "display_name": "Platform Owner",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "is_bootstrap": True
        }
        USERS_STORE[sa_username] = sa_user
        record_account_audit_event(
            action="SUPER_ADMIN_BOOTSTRAPPED",
            actor_id="SYSTEM_BOOTSTRAP",
            actor_username="SYSTEM",
            target_account_id=sa_user["user_id"],
            target_username=sa_username,
            outcome="SUCCESS",
            details={"bootstrap_method": "environment_seed"}
        )

# Execute eager synchronous initialization
_sync_init_base_users()

async def initialize_users() -> None:
    """
    Seed initial system users and execute one-time Super Admin bootstrap in persistent storage.
    Prevents duplicate accounts on subsequent application restarts.
    """
    _sync_init_base_users()

    # Sync into DB if connected
    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            for username, udata in USERS_STORE.items():
                existing = await db_client.users.find_one({"username": username})
                if not existing:
                    await db_client.users.insert_one(udata.copy())
        except Exception as e:
            logger.warning(f"Could not sync users to database: {e}")


async def get_user(username: str) -> Optional[dict]:
    """Retrieve user record by username from DB or memory store."""
    if not username:
        return None
    # 1. Check in-memory store
    if username in USERS_STORE:
        return USERS_STORE[username]
    # 2. Check database
    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            doc = await db_client.users.find_one({"username": username})
            if doc:
                USERS_STORE[username] = doc
                return doc
        except Exception:
            pass
    return None

async def get_user_by_id(user_id: str) -> Optional[dict]:
    """Retrieve user record by unique user_id."""
    if not user_id:
        return None
    for u in USERS_STORE.values():
        if u.get("user_id") == user_id:
            return u
    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            doc = await db_client.users.find_one({"user_id": user_id})
            if doc:
                USERS_STORE[doc["username"]] = doc
                return doc
        except Exception:
            pass
    return None

def strip_sensitive_fields(user: dict) -> dict:
    """Return user metadata without password hashes or internal secret keys."""
    if not user:
        return {}
    display = user.get("display_name") or user.get("full_name") or user.get("username")
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "is_active": user.get("is_active", True),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "full_name": display,
        "display_name": display
    }

async def list_admins() -> list[dict]:
    """List all accounts with role ADMIN. Strips all secret hashes."""
    # Sync from DB if available
    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            cursor = db_client.users.find({"role": UserRole.ADMIN.value})
            docs = await cursor.to_list(length=100) if hasattr(cursor, "to_list") else []
            for doc in docs:
                USERS_STORE[doc["username"]] = doc
        except Exception:
            pass

    admins = [
        strip_sensitive_fields(u)
        for u in USERS_STORE.values()
        if u.get("role") == UserRole.ADMIN.value
    ]
    return sorted(admins, key=lambda x: x.get("created_at", ""), reverse=True)

async def get_platform_summary() -> dict:
    """Return platform governance metrics for Super Admin dashboard."""
    all_users = list(USERS_STORE.values())
    admins = [u for u in all_users if u.get("role") == UserRole.ADMIN.value]
    active_admins = [u for u in admins if u.get("is_active", True)]
    inactive_admins = [u for u in admins if not u.get("is_active", True)]
    super_admins = [u for u in all_users if u.get("role") == UserRole.SUPER_ADMIN.value and u.get("is_active", True)]

    return {
        "total_admins": len(admins),
        "active_admins": len(active_admins),
        "inactive_admins": len(inactive_admins),
        "active_super_admins": len(super_admins),
        "bootstrap_complete": len(super_admins) > 0,
        "platform_role": UserRole.SUPER_ADMIN.value
    }

async def create_admin(
    actor_id: str,
    actor_username: str,
    username: str,
    password: str,
    full_name: Optional[str] = None
) -> dict:
    """Create a new Admin account with unique identity. Only callable by SUPER_ADMIN."""
    username = username.strip()
    if not username or len(username) < 3 or len(username) > 30:
        raise ValueError("Username must be between 3 and 30 characters.")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username must contain only alphanumeric characters, underscores, or hyphens.")

    env_mode = os.getenv("ENVIRONMENT", "development").lower()
    min_pwd_len = 12 if env_mode == "production" else 8
    if not password or len(password) < min_pwd_len:
        raise ValueError(f"Password must be at least {min_pwd_len} characters.")

    async with _user_lock:
        # Case-insensitive uniqueness check across in-memory store
        normalized = username.lower()
        for existing_name in USERS_STORE:
            if existing_name.lower() == normalized:
                raise FileExistsError(f"User account '{username}' already exists.")

        # Database uniqueness check
        if db_client.is_connected() and hasattr(db_client, "users"):
            try:
                db_existing = await db_client.users.find_one({"username": username})
                if db_existing:
                    raise FileExistsError(f"User account '{username}' already exists in database.")
            except FileExistsError:
                raise
            except Exception:
                pass

        user_id = f"USR-ADMIN-{uuid.uuid4().hex[:8].upper()}"
        pwd_hash = hash_password(password)
        now = _now_iso()
        display_name = full_name.strip() if full_name and full_name.strip() else username

        new_user = {
            "user_id": user_id,
            "username": username,
            "password_hash": pwd_hash,
            "role": UserRole.ADMIN.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "full_name": display_name,
            "display_name": display_name
        }

        USERS_STORE[username] = new_user
        if db_client.is_connected() and hasattr(db_client, "users"):
            try:
                await db_client.users.insert_one(new_user.copy())
            except Exception as e:
                logger.warning(f"Could not persist created admin to DB: {e}")

        record_account_audit_event(
            action="ADMIN_ACCOUNT_CREATED",
            actor_id=actor_id,
            actor_username=actor_username,
            target_account_id=user_id,
            target_username=username,
            outcome="SUCCESS",
            details={"full_name": display_name, "user_id": user_id}
        )

        return strip_sensitive_fields(new_user)

async def update_user_profile(username: str, new_display_name: str) -> dict:
    """Update display name for the specified user and persist changes."""
    user = await get_user(username)
    if not user:
        raise KeyError(f"User account '{username}' not found.")

    new_display_name = new_display_name.strip()
    if not new_display_name or len(new_display_name) > 60:
        raise ValueError("Display name must be between 1 and 60 characters.")

    now = _now_iso()
    user["full_name"] = new_display_name
    user["display_name"] = new_display_name
    user["updated_at"] = now
    USERS_STORE[username] = user

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.update_one(
                {"username": username},
                {"$set": {"full_name": new_display_name, "display_name": new_display_name, "updated_at": now}}
            )
        except Exception as e:
            logger.warning(f"Could not persist profile update for '{username}' to DB: {e}")

    record_account_audit_event(
        action="USER_PROFILE_UPDATED",
        actor_id=user.get("user_id", username),
        actor_username=username,
        target_account_id=user.get("user_id", username),
        target_username=username,
        outcome="SUCCESS",
        details={"new_display_name": new_display_name}
    )

    return strip_sensitive_fields(user)

async def set_admin_status(
    actor_id: str,
    actor_username: str,
    target_username: str,
    is_active: bool
) -> dict:
    """Activate or deactivate an Admin account. Enforces anti-lockout rules."""
    user = await get_user(target_username)
    if not user:
        raise KeyError(f"Account '{target_username}' not found.")

    # Guard: Cannot deactivate or remove Super Admin accounts
    if user.get("role") == UserRole.SUPER_ADMIN.value:
        raise PermissionError("Super Admin accounts cannot be deactivated through Admin management endpoints.")

    if user.get("role") != UserRole.ADMIN.value:
        raise ValueError("Only accounts with role 'ADMIN' can be managed via this endpoint.")

    user["is_active"] = is_active
    user["updated_at"] = _now_iso()
    USERS_STORE[target_username] = user

    if is_active:
        reactivate_user_session(target_username)
        action_name = "ADMIN_ACCOUNT_ACTIVATED"
    else:
        deactivate_user_session(target_username)
        action_name = "ADMIN_ACCOUNT_DEACTIVATED"

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.update_one(
                {"username": target_username},
                {"$set": {"is_active": is_active, "updated_at": user["updated_at"]}}
            )
        except Exception as e:
            logger.warning(f"Could not update admin status in DB: {e}")

    record_account_audit_event(
        action=action_name,
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=user.get("user_id", "UNKNOWN"),
        target_username=target_username,
        outcome="SUCCESS",
        details={"is_active": is_active}
    )

    return strip_sensitive_fields(user)

async def reset_admin_password(
    actor_id: str,
    actor_username: str,
    target_username: str,
    new_password: str
) -> dict:
    """Securely reset an Admin's password and immediately revoke all existing sessions."""
    user = await get_user(target_username)
    if not user:
        raise KeyError(f"Account '{target_username}' not found.")

    if user.get("role") != UserRole.ADMIN.value:
        raise ValueError("Only accounts with role 'ADMIN' can have their credentials reset via this endpoint.")

    env_mode = os.getenv("ENVIRONMENT", "development").lower()
    min_pwd_len = 12 if env_mode == "production" else 8
    if not new_password or len(new_password) < min_pwd_len:
        raise ValueError(f"New password must be at least {min_pwd_len} characters.")

    user["password_hash"] = hash_password(new_password)
    user["updated_at"] = _now_iso()
    USERS_STORE[target_username] = user

    # Invalidate all prior sessions immediately
    revoke_user_sessions(target_username)

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.update_one(
                {"username": target_username},
                {"$set": {"password_hash": user["password_hash"], "updated_at": user["updated_at"]}}
            )
        except Exception as e:
            logger.warning(f"Could not update admin password in DB: {e}")

    record_account_audit_event(
        action="ADMIN_ACCESS_RESET",
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=user.get("user_id", "UNKNOWN"),
        target_username=target_username,
        outcome="SUCCESS",
        details={"reason": "Administrative credential reset by Super Admin"}
    )

    return strip_sensitive_fields(user)

async def remove_admin(
    actor_id: str,
    actor_username: str,
    target_username: str,
    confirmation: bool
) -> dict:
    """Safely remove an Admin account. Requires explicit confirmation."""
    if not confirmation:
        raise ValueError("Explicit confirmation (confirm=True) is required to remove an administrator account.")

    user = await get_user(target_username)
    if not user:
        raise KeyError(f"Account '{target_username}' not found.")

    if user.get("role") == UserRole.SUPER_ADMIN.value:
        raise PermissionError("Super Admin accounts cannot be deleted.")

    if user.get("role") != UserRole.ADMIN.value:
        raise ValueError("Only accounts with role 'ADMIN' can be removed via this endpoint.")

    target_id = user.get("user_id", "UNKNOWN")
    USERS_STORE.pop(target_username, None)

    # Invalidate sessions permanently
    deactivate_user_session(target_username)
    revoke_user_sessions(target_username)

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.delete_one({"username": target_username})
        except Exception as e:
            logger.warning(f"Could not delete admin from DB: {e}")

    record_account_audit_event(
        action="ADMIN_ACCOUNT_REMOVED",
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=target_id,
        target_username=target_username,
        outcome="SUCCESS",
        details={"confirmation": True}
    )

    return {
        "status": "success",
        "message": f"Administrator account '{target_username}' has been safely removed.",
        "removed_user_id": target_id
    }


# =============================================================================
# EMPLOYEE MANAGEMENT SERVICE FUNCTIONS (ADMIN EXCLUSIVE)
# =============================================================================

async def list_employees() -> list[dict]:
    """List all accounts with role EMPLOYEE. Strips all secret hashes."""
    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            cursor = db_client.users.find({"role": UserRole.EMPLOYEE.value})
            docs = await cursor.to_list(length=200) if hasattr(cursor, "to_list") else []
            for doc in docs:
                USERS_STORE[doc["username"]] = doc
        except Exception:
            pass

    employees = [
        strip_sensitive_fields(u)
        for u in USERS_STORE.values()
        if u.get("role") == UserRole.EMPLOYEE.value
    ]
    return sorted(employees, key=lambda x: x.get("created_at", ""), reverse=True)


async def create_employee(
    actor_id: str,
    actor_username: str,
    username: str,
    password: str,
    full_name: Optional[str] = None
) -> dict:
    """Create a new Employee account. Callable by ADMIN."""
    username = username.strip()
    if not username or len(username) < 3 or len(username) > 30:
        raise ValueError("Username must be between 3 and 30 characters.")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username must contain only alphanumeric characters, underscores, or hyphens.")

    env_mode = os.getenv("ENVIRONMENT", "development").lower()
    min_pwd_len = 12 if env_mode == "production" else 8
    if not password or len(password) < min_pwd_len:
        raise ValueError(f"Password must be at least {min_pwd_len} characters.")

    async with _user_lock:
        normalized = username.lower()
        for existing_name in USERS_STORE:
            if existing_name.lower() == normalized:
                raise FileExistsError(f"User account '{username}' already exists.")

        if db_client.is_connected() and hasattr(db_client, "users"):
            try:
                db_existing = await db_client.users.find_one({"username": username})
                if db_existing:
                    raise FileExistsError(f"User account '{username}' already exists in database.")
            except FileExistsError:
                raise
            except Exception:
                pass

        user_id = f"USR-EMP-{uuid.uuid4().hex[:8].upper()}"
        pwd_hash = hash_password(password)
        now = _now_iso()
        display_name = full_name.strip() if full_name and full_name.strip() else username

        new_user = {
            "user_id": user_id,
            "username": username,
            "password_hash": pwd_hash,
            "role": UserRole.EMPLOYEE.value,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "full_name": display_name,
            "display_name": display_name,
            "created_by": actor_username
        }

        USERS_STORE[username] = new_user
        if db_client.is_connected() and hasattr(db_client, "users"):
            try:
                await db_client.users.insert_one(new_user.copy())
            except Exception as e:
                logger.warning(f"Could not persist created employee to DB: {e}")

        record_account_audit_event(
            action="EMPLOYEE_ACCOUNT_CREATED",
            actor_id=actor_id,
            actor_username=actor_username,
            target_account_id=user_id,
            target_username=username,
            outcome="SUCCESS",
            details={"full_name": display_name, "user_id": user_id}
        )

        return strip_sensitive_fields(new_user)


async def set_employee_status(
    actor_id: str,
    actor_username: str,
    target_username: str,
    is_active: bool
) -> dict:
    """Activate or deactivate an Employee account."""
    user = await get_user(target_username)
    if not user:
        raise KeyError(f"Account '{target_username}' not found.")

    if user.get("role") != UserRole.EMPLOYEE.value:
        raise ValueError("Only accounts with role 'EMPLOYEE' can be managed via this endpoint.")

    user["is_active"] = is_active
    user["updated_at"] = _now_iso()
    USERS_STORE[target_username] = user

    if is_active:
        reactivate_user_session(target_username)
        action_name = "EMPLOYEE_ACCOUNT_ACTIVATED"
    else:
        deactivate_user_session(target_username)
        action_name = "EMPLOYEE_ACCOUNT_DEACTIVATED"

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.update_one(
                {"username": target_username},
                {"$set": {"is_active": is_active, "updated_at": user["updated_at"]}}
            )
        except Exception as e:
            logger.warning(f"Could not update employee status in DB: {e}")

    record_account_audit_event(
        action=action_name,
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=user.get("user_id", "UNKNOWN"),
        target_username=target_username,
        outcome="SUCCESS",
        details={"is_active": is_active}
    )

    return strip_sensitive_fields(user)


async def reset_employee_password(
    actor_id: str,
    actor_username: str,
    target_username: str,
    new_password: str
) -> dict:
    """Reset an Employee's password and immediately revoke all existing sessions."""
    user = await get_user(target_username)
    if not user:
        raise KeyError(f"Account '{target_username}' not found.")

    if user.get("role") != UserRole.EMPLOYEE.value:
        raise ValueError("Only accounts with role 'EMPLOYEE' can have credentials reset via this endpoint.")

    env_mode = os.getenv("ENVIRONMENT", "development").lower()
    min_pwd_len = 12 if env_mode == "production" else 8
    if not new_password or len(new_password) < min_pwd_len:
        raise ValueError(f"New password must be at least {min_pwd_len} characters.")

    user["password_hash"] = hash_password(new_password)
    user["updated_at"] = _now_iso()
    USERS_STORE[target_username] = user

    revoke_user_sessions(target_username)

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.update_one(
                {"username": target_username},
                {"$set": {"password_hash": user["password_hash"], "updated_at": user["updated_at"]}}
            )
        except Exception as e:
            logger.warning(f"Could not update employee password in DB: {e}")

    record_account_audit_event(
        action="EMPLOYEE_ACCESS_RESET",
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=user.get("user_id", "UNKNOWN"),
        target_username=target_username,
        outcome="SUCCESS",
        details={"reason": "Credential reset by Administrator"}
    )

    return strip_sensitive_fields(user)


async def remove_employee(
    actor_id: str,
    actor_username: str,
    target_username: str,
    confirmation: bool
) -> dict:
    """Safely remove an Employee account. Requires explicit confirmation."""
    if not confirmation:
        raise ValueError("Explicit confirmation (confirm=True) is required to remove an employee account.")

    user = await get_user(target_username)
    if not user:
        raise KeyError(f"Account '{target_username}' not found.")

    if user.get("role") != UserRole.EMPLOYEE.value:
        raise ValueError("Only accounts with role 'EMPLOYEE' can be removed via this endpoint.")

    target_id = user.get("user_id", "UNKNOWN")
    USERS_STORE.pop(target_username, None)

    deactivate_user_session(target_username)
    revoke_user_sessions(target_username)

    if db_client.is_connected() and hasattr(db_client, "users"):
        try:
            await db_client.users.delete_one({"username": target_username})
        except Exception as e:
            logger.warning(f"Could not delete employee from DB: {e}")

    record_account_audit_event(
        action="EMPLOYEE_ACCOUNT_REMOVED",
        actor_id=actor_id,
        actor_username=actor_username,
        target_account_id=target_id,
        target_username=target_username,
        outcome="SUCCESS",
        details={"confirmation": True}
    )

    return {
        "status": "success",
        "message": f"Employee account '{target_username}' has been safely removed.",
        "removed_user_id": target_id
    }


def get_account_audit_logs(limit: int = 50) -> list[dict]:
    """Return account management audit trail without sensitive values."""
    return ACCOUNT_AUDIT_LOGS[:limit]
