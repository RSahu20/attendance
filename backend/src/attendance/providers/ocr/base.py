from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL.Image import Image


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class OCRProvider(ABC):
    @abstractmethod
    def extract(self, image: Image) -> OCRResult:
        """Extract text and a normalized confidence between zero and one."""
