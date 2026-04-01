import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class RAGSettings:
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str
    firecrawl_api_key: str
    embedding_model_name: str
    answer_model_name: str
    rerank_threshold: float
    trusted_threshold: float
    firecrawl_timeout_ms: int
    trusted_web_search_limit: int
    trusted_web_max_scrapes: int
    min_legal_evidence: int
    min_trusted_evidence: int
    rag_port: int

    @classmethod
    def from_env(cls) -> "RAGSettings":
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", "").strip(),
            embedding_model_name=os.getenv("HF_EMBED_MODEL", os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")).strip(),
            answer_model_name=os.getenv("ANSWER_MODEL", "gpt-4o-mini").strip(),
            rerank_threshold=float(os.getenv("RAG_LEGAL_SCORE_THRESHOLD", "0.45")),
            trusted_threshold=float(os.getenv("RAG_TRUSTED_SCORE_THRESHOLD", "0.38")),
            firecrawl_timeout_ms=int(os.getenv("FIRECRAWL_TIMEOUT_MS", "45000")),
            trusted_web_search_limit=int(os.getenv("TRUSTED_WEB_SEARCH_LIMIT", "3")),
            trusted_web_max_scrapes=int(os.getenv("TRUSTED_WEB_MAX_SCRAPES", "3")),
            min_legal_evidence=int(os.getenv("RAG_MIN_LEGAL_EVIDENCE", "2")),
            min_trusted_evidence=int(os.getenv("RAG_MIN_TRUSTED_EVIDENCE", "2")),
            rag_port=int(os.getenv("RAG_PORT", "8000")),
        )
