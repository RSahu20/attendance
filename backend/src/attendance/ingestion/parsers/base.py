from abc import ABC, abstractmethod

from attendance.ingestion.types import ParsedUnit


class DocumentParser(ABC):
    name: str
    version = "1.0"

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> list[ParsedUnit]:
        """Extract format-neutral source units without creating database rows."""
