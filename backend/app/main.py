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
    reports
)

load_dotenv()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: attempt database connection with graceful fallback
    try:
        await db_client.connect()
    except Exception as e:
        logger.warning(f"MongoDB offline on startup, continuing with resilient in-memory fallback: {e}")
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
origins = [
    "http://localhost",
    "http://localhost:5500",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers under /api
app.include_router(auth.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(evidence.router, prefix="/api")
app.include_router(blockchain.router, prefix="/api")
app.include_router(custody.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(verification.router, prefix="/api")
app.include_router(reports.router, prefix="/api")

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "ChainVault API"
    }
