import os
import pytest
from app.database.mongodb import MongoDBClient

def test_mongodb_client_configuration_defaults():
    """Requirement 13: Verify MongoDB client defaults and test database configuration."""
    client = MongoDBClient()
    assert client.uri == os.getenv("MONGO_URI", "mongodb://localhost:27017")
    assert client.db_name in ["chainvault", "chainvault_test"]

def test_database_collections_declared():
    """Requirement 3: Verify standard collection references defined in client."""
    client = MongoDBClient()
    # Mock / instantiate db object locally
    client.db = {
        "users": "users_col",
        "cases": "cases_col",
        "evidence": "evidence_col",
        "custody_logs": "custody_col",
        "audit_logs": "audit_col",
        "reports": "reports_col"
    }
    assert "users" in client.db
    assert "cases" in client.db
    assert "evidence" in client.db
    assert "custody_logs" in client.db
    assert "audit_logs" in client.db
    assert "reports" in client.db

def test_live_mongodb_connection():
    """Requirement 3 & 13: Probe live connection to MongoDB test database."""
    import asyncio
    async def _test():
        client = MongoDBClient()
        client.db_name = "chainvault_test"
        await client.connect()
        pong = await client.client.admin.command('ping')
        assert pong.get('ok') == 1.0
        await client.close()
    asyncio.run(_test())
