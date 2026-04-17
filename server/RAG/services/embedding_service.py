from typing import Any, List, Optional

from openai import OpenAI
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    def __init__(self, settings: Any, embedding_model: Optional[SentenceTransformer] = None) -> None:
        self.settings = settings
        self.embedding_model = embedding_model
        self.client: Optional[OpenAI] = None

        if self.embedding_model is None and hasattr(settings, "embedding_model_name"):
            self.embedding_model = SentenceTransformer(settings.embedding_model_name)
        elif self.embedding_model is None:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        if not text.strip():
            return None
        if self.embedding_model is not None:
            return self.embedding_model.encode(text, normalize_embeddings=True).tolist()

        response = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=text,
            dimensions=self.settings.embedding_dimensions,
        )
        return response.data[0].embedding if response.data else None

    @staticmethod
    def to_pgvector(vector: Optional[List[float]]) -> Optional[str]:
        if not vector:
            return None
        return "[" + ",".join(f"{value:.10f}" for value in vector) + "]"
