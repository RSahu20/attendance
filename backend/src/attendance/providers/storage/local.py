import os
from pathlib import Path

from attendance.providers.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if self.root not in path.parents:
            raise ValueError("Invalid storage key")
        return path

    def store(self, storage_key: str, content: bytes) -> None:
        target = self._resolve(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)

    def read(self, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        self._resolve(storage_key).unlink(missing_ok=True)
