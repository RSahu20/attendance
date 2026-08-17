from attendance.providers.embeddings.base import EmbeddingProvider
from attendance.providers.embeddings.sentence_transformer import SentenceTransformerProvider

__all__ = ["EmbeddingProvider", "SentenceTransformerProvider"]
