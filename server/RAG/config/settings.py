import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class RAGSettings:
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str
    embedding_model_name: str
    answer_model_name: str
    firecrawl_api_key: str
    rag_legal_score_threshold: float
    rag_trusted_score_threshold: float
    rag_min_legal_evidence: int
    rag_min_trusted_evidence: int
    firecrawl_timeout_ms: int
    trusted_web_search_limit: int
    trusted_web_max_scrapes: int
    trusted_web_max_sources: int
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection_session_docs: str
    qdrant_collection_global_docs: str
    session_doc_top_k: int
    session_doc_score_threshold: float
    session_doc_ttl_hours: int
    session_doc_chunk_size: int
    session_doc_chunk_overlap: int
    global_doc_top_k: int
    global_doc_score_threshold: float
    rag_port: int
    rerank_model_name: str
    rerank_candidate_count: int
    rerank_final_top_k: int

    @classmethod
    def from_env(cls) -> "RAGSettings":
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", "").strip(),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            embedding_model_name=os.getenv(
                "HF_EMBED_MODEL",
                os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large"),
            ).strip(),
            answer_model_name=os.getenv("ANSWER_MODEL", "gpt-4o-mini").strip(),
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", "").strip(),
            rag_legal_score_threshold=float(os.getenv("RAG_LEGAL_SCORE_THRESHOLD", "0.45")),
            rag_trusted_score_threshold=float(os.getenv("RAG_TRUSTED_SCORE_THRESHOLD", "0.38")),
            rag_min_legal_evidence=int(os.getenv("RAG_MIN_LEGAL_EVIDENCE", "2")),
            rag_min_trusted_evidence=int(os.getenv("RAG_MIN_TRUSTED_EVIDENCE", "1")),
            firecrawl_timeout_ms=int(os.getenv("FIRECRAWL_TIMEOUT_MS", "45000")),
            trusted_web_search_limit=int(os.getenv("TRUSTED_WEB_SEARCH_LIMIT", "3")),
            trusted_web_max_scrapes=int(os.getenv("TRUSTED_WEB_MAX_SCRAPES", "3")),
            trusted_web_max_sources=int(os.getenv("TRUSTED_WEB_MAX_SOURCES", "5")),
            qdrant_url=os.getenv("QDRANT_URL", os.getenv("QDRANT_ENDPOINT", "")).strip(),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", os.getenv("QDRANT_KEY", "")).strip(),
            qdrant_collection_session_docs=os.getenv("QDRANT_COLLECTION_SESSION_DOCS", "session_docs").strip(),
            qdrant_collection_global_docs=os.getenv("QDRANT_COLLECTION_GLOBAL_DOCS", "global_docs").strip(),
            session_doc_top_k=int(os.getenv("SESSION_DOC_TOP_K", "5")),
            session_doc_score_threshold=float(os.getenv("SESSION_DOC_SCORE_THRESHOLD", "0.55")),
            session_doc_ttl_hours=int(os.getenv("SESSION_DOC_TTL_HOURS", "24")),
            session_doc_chunk_size=int(os.getenv("SESSION_DOC_CHUNK_SIZE", "900")),
            session_doc_chunk_overlap=int(os.getenv("SESSION_DOC_CHUNK_OVERLAP", "120")),
            global_doc_top_k=int(os.getenv("GLOBAL_DOC_TOP_K", "5")),
            global_doc_score_threshold=float(os.getenv("GLOBAL_DOC_SCORE_THRESHOLD", "0.55")),
            rag_port=int(os.getenv("RAG_PORT", "8000")),
            rerank_model_name=os.getenv("RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3").strip(),
            rerank_candidate_count=int(os.getenv("RERANK_CANDIDATE_COUNT", "10")),
            rerank_final_top_k=int(os.getenv("RERANK_FINAL_TOP_K", "5")),
        )

    @property
    def rerank_threshold(self) -> float:
        return self.rag_legal_score_threshold

    @property
    def min_legal_evidence(self) -> int:
        return self.rag_min_legal_evidence

    @property
    def trusted_threshold(self) -> float:
        return self.rag_trusted_score_threshold
