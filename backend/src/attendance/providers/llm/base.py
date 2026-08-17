from abc import ABC, abstractmethod

from attendance.domain.generation import LLMRequest, ProviderOutput


class LLMProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate(self, request: LLMRequest) -> ProviderOutput:
        """Generate typed output from already-authorized context only."""
