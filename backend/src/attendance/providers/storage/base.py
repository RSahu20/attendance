from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    def store(self, storage_key: str, content: bytes) -> None:
        """Persist bytes under an application-generated opaque key."""

    @abstractmethod
    def read(self, storage_key: str) -> bytes:
        """Read bytes previously stored under the key."""

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Delete a key if it exists."""
