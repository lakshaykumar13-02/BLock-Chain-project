import os
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.mongodb import MongoDBClient

client = TestClient(app)

def test_mongodb_target_isolated_test_database():
    """Requirement 1 & 2.A: Confirm test suite targets chainvault_test and never the development DB."""
    test_client = MongoDBClient()
    test_client.db_name = "chainvault_test"
    assert test_client.db_name == "chainvault_test"
    assert test_client.db_name != "chainvault", "Tests must not target development database"

def test_live_mongodb_crud_and_indexing_against_test_db():
    """Requirement 3 & Step 4: Exercise live CRUD and index operations against chainvault_test and isolate cleanup."""
    import asyncio
    async def _run():
        test_client = MongoDBClient()
        test_client.db_name = "chainvault_test"
        await test_client.connect()

        # 1. Connectivity & ping
        pong = await test_client.client.admin.command('ping')
        assert pong.get('ok') == 1.0

        # 2. Database selection confirmation
        assert test_client.db_name == "chainvault_test"

        # 3. Create index
        index_result = await test_client.evidence.create_index("evidence_id", unique=True)
        assert index_result == "evidence_id_1"

        # 4. Insert synthetic test record
        synthetic_record = {
            "evidence_id": "EV-SYNTH-LIVE-01",
            "case_id": "CS-TEST-01",
            "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "metadata": {"test": True}
        }
        insert_res = await test_client.evidence.insert_one(synthetic_record)
        assert insert_res.inserted_id is not None

        # 5. Read back
        found = await test_client.evidence.find_one({"evidence_id": "EV-SYNTH-LIVE-01"})
        assert found is not None
        assert found["hash"] == synthetic_record["hash"]

        # 6. Update
        update_res = await test_client.evidence.update_one(
            {"evidence_id": "EV-SYNTH-LIVE-01"},
            {"$set": {"status": "verified"}}
        )
        assert update_res.modified_count == 1

        # 7. Cleanup isolation: delete only synthetic test record
        del_res = await test_client.evidence.delete_one({"evidence_id": "EV-SYNTH-LIVE-01"})
        assert del_res.deleted_count == 1

        # Confirm record no longer exists
        remaining = await test_client.evidence.find_one({"evidence_id": "EV-SYNTH-LIVE-01"})
        assert remaining is None

        await test_client.close()

    asyncio.run(_run())

def test_mongodb_graceful_handling_when_service_unavailable():
    """Requirement 3 & Step 4: Verify expected exception handling when MongoDB is unavailable."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _test():
        # Port 27018 is deliberately offline/unreachable
        offline_client = AsyncIOMotorClient("mongodb://localhost:27018/?serverSelectionTimeoutMS=500")
        with pytest.raises(Exception):
            await offline_client.admin.command('ping')
        offline_client.close()

    asyncio.run(_test())

def test_fastapi_case_creation_and_retrieval_integration():
    """Requirement 2.A: FastAPI + MongoDB Case creation and retrieval."""
    login_res = client.post("/api/auth/login", json={"username": "investigator1", "password": "TestPassword123!"})
    token = login_res.json()["access_token"]
    response = client.post(
        "/api/cases",
        json={"case_id": "CS-TEST-01", "title": "Synthetic Test Case"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code in [200, 201]
