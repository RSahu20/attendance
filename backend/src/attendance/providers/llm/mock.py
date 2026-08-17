from attendance.domain.generation import LLMRequest, ProviderCitation, ProviderOutput
from attendance.providers.llm.base import LLMProvider


class MockProvider(LLMProvider):
    name = "mock"
    model = "deterministic-grounded-mock-v1"

    def generate(self, request: LLMRequest) -> ProviderOutput:
        evidence = request.context.evidence
        if not evidence:
            return ProviderOutput(answer="No authorized document evidence is available.")
        item = evidence[0]
        prefix = "Authorized evidence indicates"
        if request.context.structured_result:
            value = request.context.structured_result.get("value")
            prefix = f"The authorized structured result is {value}. Supporting evidence indicates"
        return ProviderOutput(
            answer=f"{prefix}: {item.content}",
            citations=[ProviderCitation(evidence_id=item.evidence_id, claim=item.content)],
        )
