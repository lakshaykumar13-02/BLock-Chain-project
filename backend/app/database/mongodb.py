from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class MongoDBClient:
    def __init__(self):
        self.client = None
        self.db = None
        
        # Load from environment variables
        self.uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = os.getenv("MONGO_DB_NAME", "chainvault")

    async def connect(self):
        try:
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.db_name]
            
            # Prepare collections
            self.users = self.db["users"]
            self.cases = self.db["cases"]
            self.evidence = self.db["evidence"]
            self.custody_logs = self.db["custody_logs"]
            self.audit_logs = self.db["audit_logs"]
            self.reports = self.db["reports"]
            
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.error(f"Could not connect to MongoDB: {e}")
            raise e

    async def close(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")

db_client = MongoDBClient()
