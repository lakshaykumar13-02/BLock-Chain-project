"""
ChainVault Database Abstraction & Multi-Backend Architecture
============================================================
Supports both MongoDB (Motor async driver) and Google Cloud Firestore
(asynchronous AsyncClient). Default backend remains MongoDB unless explicitly
configured via DATABASE_BACKEND=firestore.
"""

from .base import BaseDatabaseClient
from .mongodb import MongoDBClient, db_client, get_database_client
from .firestore import FirestoreClient

__all__ = [
    "BaseDatabaseClient",
    "MongoDBClient",
    "FirestoreClient",
    "db_client",
    "get_database_client"
]
