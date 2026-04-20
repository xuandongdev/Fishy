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

    def generate_embedding(self, text: str, prefix: str = "") -> Optional[List[float]]:
        if not text.strip():
            return None
        model_input = f"{prefix}{text}" if prefix else text
        if self.embedding_model is not None:
            return self.embedding_model.encode(model_input, normalize_embeddings=True).tolist()

        response = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=model_input,
            dimensions=self.settings.embedding_dimensions,
        )
        return response.data[0].embedding if response.data else None

    def generate_embeddings(self, texts: List[str], prefix: str = "") -> List[List[float]]:
        clean_texts = [text for text in texts if text and text.strip()]
        if not clean_texts:
            return []
        model_inputs = [f"{prefix}{text}" if prefix else text for text in clean_texts]
        if self.embedding_model is not None:
            return self.embedding_model.encode(model_inputs, normalize_embeddings=True).tolist()
        response = self.client.embeddings.create(
            model=self.settings.embedding_model,
            input=model_inputs,
            dimensions=self.settings.embedding_dimensions,
        )
        return [item.embedding for item in response.data]

    def generate_query_embedding(self, text: str) -> Optional[List[float]]:
        return self.generate_embedding(text, prefix="query: ")

    def generate_passage_embedding(self, text: str) -> Optional[List[float]]:
        return self.generate_embedding(text, prefix="passage: ")

    def generate_passage_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self.generate_embeddings(texts, prefix="passage: ")

    def generate_rela_embedding(self, canonical_action: str, aliases: List[str]) -> Optional[List[float]]:
        alias_text = ", ".join(alias.strip() for alias in aliases if alias and alias.strip())
        if not canonical_action.strip() and not alias_text:
            return None
        blended = " ".join(part for part in [canonical_action.strip(), alias_text] if part).strip()
        return self.generate_passage_embedding(blended)

    @property
    def vector_size(self) -> int:
        if self.embedding_model is not None:
            return len(self.generate_embedding("vector size probe") or [])
        return int(getattr(self.settings, "embedding_dimensions", 0))

    @staticmethod
    def to_pgvector(vector: Optional[List[float]]) -> Optional[str]:
        if not vector:
            return None
        return "[" + ",".join(f"{value:.10f}" for value in vector) + "]"
