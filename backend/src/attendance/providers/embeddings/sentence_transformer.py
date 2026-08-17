from attendance.providers.embeddings.base import EmbeddingProvider


class SentenceTransformerProvider(EmbeddingProvider):
    model_version = "1"
    dimension = 384

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]
