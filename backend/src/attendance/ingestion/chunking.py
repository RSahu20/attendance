from dataclasses import dataclass
from typing import Any

from attendance.ingestion.types import ParsedUnit


@dataclass(frozen=True)
class ChunkDraft:
    chunk_key: str
    content: str
    source_locator: dict[str, Any]
    token_count: int


class DocumentChunker:
    def __init__(self, max_characters: int = 2000) -> None:
        self.max_characters = max_characters

    def chunk(self, unit: ParsedUnit) -> list[ChunkDraft]:
        content = unit.raw_text.strip()
        if not content:
            return []
        parts = [
            content[offset : offset + self.max_characters]
            for offset in range(0, len(content), self.max_characters)
        ]
        return [
            ChunkDraft(
                chunk_key=f"{unit.source_unit_key}:chunk:{index}",
                content=part,
                source_locator=unit.source_locator,
                token_count=len(part.split()),
            )
            for index, part in enumerate(parts, start=1)
        ]
