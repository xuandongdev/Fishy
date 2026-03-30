from typing import List, Optional

from openai import OpenAI

from schema.legal_ingest_schema import LegalIngestSettings


class EmbeddingService:
    def __init__(self, settings: LegalIngestSettings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        if not text.strip():
            return None
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
