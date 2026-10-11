from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from .database.mongodb import db_client

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db_client.connect()
    yield
    # Shutdown
    await db_client.close()

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

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "ChainVault API"
    }
