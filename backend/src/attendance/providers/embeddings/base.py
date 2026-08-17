from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    model_name: str
    model_version: str
    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one normalized embedding per input text."""
