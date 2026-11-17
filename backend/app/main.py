import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from .database.mongodb import db_client
from .routes import (
    auth,
    cases,
    evidence,
    blockchain,
    custody,
    audit,
    verification,
    reports,
    recovery,
    super_admin,
    employees,
    tasks
)
from .services.user_service import initialize_users

load_dotenv()
logger = logging.getLogger(__name__)

def validate_production_preflight_config():
    """
    Validates operational configuration when running in production.
    Rejects placeholder secrets, missing persistent storage, missing MongoDB configuration,
    and invalid blockchain chain or contract configuration.
    """
    env_mode = os.getenv("ENVIRONMENT", "development").lower()
    if env_mode != "production":
        return

    # 1. JWT Secret validation
    from .security.auth import JWT_SECRET, KNOWN_PLACEHOLDER_SECRETS
    jwt_sec = os.getenv("JWT_SECRET", JWT_SECRET)
    if jwt_sec in KNOWN_PLACEHOLDER_SECRETS or len(jwt_sec) < 32:
        raise RuntimeError("CRITICAL: Production mode rejects default, placeholder, or short (<32 chars) JWT_SECRET.")

    # 2. Blockchain configuration validation
    from .services.blockchain import RPC_URL, CONTRACT_ADDRESS, EXPECTED_CHAIN_ID
    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", RPC_URL)
    contract_addr = os.getenv("CONTRACT_ADDRESS", CONTRACT_ADDRESS)
    try:
        chain_id = int(os.getenv("BLOCKCHAIN_CHAIN_ID", EXPECTED_CHAIN_ID))
    except (ValueError, TypeError):
        chain_id = 0

    if "YOUR_INFURA" in rpc_url or "YOUR_ALCHEMY" in rpc_url or "PROJECT_ID" in rpc_url:
        raise RuntimeError("CRITICAL: Production mode rejects placeholder BLOCKCHAIN_RPC_URL.")
    if chain_id == 31337:
        raise RuntimeError("CRITICAL: Production mode cannot target local Hardhat testnet (chain ID 31337).")
    if "127.0.0.1" in rpc_url or "localhost" in rpc_url:
        raise RuntimeError(f"CRITICAL: Production mode cannot target localhost RPC: {rpc_url}")
    if not contract_addr or contract_addr == "0x0000000000000000000000000000000000000000" or len(contract_addr) != 42 or not contract_addr.startswith("0x"):
        raise RuntimeError(f"CRITICAL: Production mode requires a valid non-zero CONTRACT_ADDRESS: {contract_addr}")

    # 3. Persistent storage paths validation
    from .services.storage import get_storage_path
    from .services.report import get_reports_dir
    try:
        sp = get_storage_path()
        rp = get_reports_dir()
        test_file_s = sp / ".write_test"
        test_file_s.write_text("ok")
        test_file_s.unlink()
        test_file_r = rp / ".write_test"
        test_file_r.write_text("ok")
        test_file_r.unlink()
    except Exception as e:
        raise RuntimeError(f"CRITICAL: Production persistent storage directories are not writable: {e}")

    # 4. Admin credential validation for production
    admin_pwd = os.getenv("ADMIN_INITIAL_PASSWORD")
    if not admin_pwd or admin_pwd == "AdminPassword123!" or len(admin_pwd) < 12:
        raise RuntimeError("CRITICAL: Production mode requires ADMIN_INITIAL_PASSWORD to be explicitly configured with a non-default credential (min 12 characters).")

    # 5. Persistent storage requirement
    if os.getenv("REQUIRE_PERSISTENT_STORAGE", "").lower() != "true":
        raise RuntimeError("CRITICAL: Production mode requires REQUIRE_PERSISTENT_STORAGE=true.")

    # 6. Database and Firebase credentials validation
    backend_mode = os.getenv("DATABASE_BACKEND", "mongodb").lower()
    if backend_mode == "firestore":
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        if not project_id:
            raise RuntimeError("CRITICAL: Production mode with Firestore backend requires FIREBASE_PROJECT_ID.")
        if os.getenv("FIRESTORE_EMULATOR_HOST"):
            raise RuntimeError("CRITICAL: Production mode cannot target FIRESTORE_EMULATOR_HOST.")
        sa_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if sa_creds and not os.path.exists(sa_creds):
            raise RuntimeError(f"CRITICAL: GOOGLE_APPLICATION_CREDENTIALS points to nonexistent file: {sa_creds}")
    elif backend_mode == "mongodb":
        mongo_uri = os.getenv("MONGO_URI", "")
        if not mongo_uri or "localhost" in mongo_uri or "127.0.0.1" in mongo_uri:
            raise RuntimeError("CRITICAL: Production mode requires a remote, authenticated MONGO_URI (e.g. MongoDB Atlas replica set).")

    # 7. HTTPS, QR and Verification URL validation
    allow_local_qr = os.getenv("ALLOW_LOCAL_QR_LINKS", "false").lower()
    if allow_local_qr == "true":
        raise RuntimeError("CRITICAL: Production mode forbids ALLOW_LOCAL_QR_LINKS=true.")
    verification_base = os.getenv("PUBLIC_VERIFICATION_URL_BASE", "")
    if not verification_base.startswith("https://"):
        raise RuntimeError("CRITICAL: Production mode requires PUBLIC_VERIFICATION_URL_BASE to start with 'https://'.")

    # 8. CORS origins validation
    cors_env = os.getenv("CORS_ORIGINS", "")
    if "*" in cors_env:
        raise RuntimeError("CRITICAL: Production mode forbids wildcard '*' in CORS_ORIGINS.")

    # 9. Super Admin initial credential validation
    sa_pwd = os.getenv("SUPER_ADMIN_INITIAL_PASSWORD")
    if sa_pwd:
        if len(sa_pwd) < 12 or sa_pwd in ("password", "admin", "changeme", "superadmin", "SuperAdmin123!", "AdminPassword123!"):
            raise RuntimeError("CRITICAL: Production mode requires SUPER_ADMIN_INITIAL_PASSWORD to be a strong non-default credential (min 12 characters).")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preflight configuration validation in production mode
    validate_production_preflight_config()

    # Startup: attempt database connection with graceful fallback unless persistent storage required
    try:
        await db_client.connect()
    except Exception as e:
        if db_client.require_persistent_storage:
            logger.critical(f"FATAL: Persistent storage required but database connection failed: {e}")
            raise
        logger.warning(f"Database offline on startup, continuing with resilient in-memory fallback: {e}")

    # Seed users and bootstrap Super Admin
    try:
        await initialize_users()
    except Exception as e:
        logger.warning(f"User initialization notice: {e}")

    yield
    # Shutdown
    try:
        await db_client.close()
    except Exception:
        pass

app = FastAPI(
    title="ChainVault API",
    description="Blockchain-Based Digital Evidence Integrity & Chain-of-Custody Platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
default_origins = [
    "http://localhost",
    "http://localhost:5500",
    "http://localhost:5501",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:5501",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:3000"
]
cors_env = os.getenv("CORS_ORIGINS")
origins = [o.strip() for o in cors_env.split(",") if o.strip()] if cors_env else default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request, call_next):
    """Inject defensive HTTP security headers into all API responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
    return response


# Mount Routers under /api

app.include_router(auth.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(evidence.router, prefix="/api")
app.include_router(blockchain.router, prefix="/api")
app.include_router(custody.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(verification.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(recovery.router, prefix="/api")
app.include_router(super_admin.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "ChainVault API"}
