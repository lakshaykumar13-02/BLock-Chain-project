from abc import ABC, abstractmethod
from typing import Any, Optional

class BaseDatabaseClient(ABC):
    """Abstract interface defining persistence contracts for ChainVault."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the persistent database."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Gracefully terminate database connections."""
        pass

    @abstractmethod
    async def ping(self) -> bool:
        """Verify live database connectivity and responsiveness."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if database client is actively initialized."""
        pass

    @abstractmethod
    def get_persistence_mode(self) -> str:
        """Return diagnostic persistence status."""
        pass

    @property
    @abstractmethod
    def users(self) -> Any:
        pass

    @property
    @abstractmethod
    def cases(self) -> Any:
        pass

    @property
    @abstractmethod
    def evidence(self) -> Any:
        pass

    @property
    @abstractmethod
    def custody_logs(self) -> Any:
        pass

    @property
    @abstractmethod
    def audit_logs(self) -> Any:
        pass

    @property
    @abstractmethod
    def reports(self) -> Any:
        pass

    @property
    @abstractmethod
    def blockchain_checkpoints(self) -> Any:
        pass

    @property
    @abstractmethod
    def custody_transactions(self) -> Any:
        pass

    @property
    @abstractmethod
    def tasks(self) -> Any:
        pass

    @property
    @abstractmethod
    def db(self) -> Any:
        pass
