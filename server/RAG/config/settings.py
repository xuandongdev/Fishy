import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _parse_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class RAGSettings:
    supabase_url: str
    supabase_service_role_key: str
    openai_api_key: str
    embedding_model_name: str
    answer_model_name: str
    classifier_model_name: str
    classifier_timeout_seconds: float
    rag_legal_score_threshold: float
    rag_min_legal_evidence: int
    legal_retrieval_rpc_name: str
    legacy_legal_retrieval_rpc_name: str
    global_doc_top_k: int
    global_doc_score_threshold: float
    rag_port: int
    rerank_model_name: str
    rerank_candidate_count: int
    rerank_final_top_k: int
    chat_metrics_csv_enabled: bool
    chat_metrics_csv_path: str

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
            classifier_model_name=os.getenv("CLASSIFIER_MODEL", "gpt-4.1-nano").strip(),
            classifier_timeout_seconds=float(os.getenv("CLASSIFIER_TIMEOUT_SECONDS", "2.5")),
            rag_legal_score_threshold=float(os.getenv("RAG_LEGAL_SCORE_THRESHOLD", "0.45")),
            rag_min_legal_evidence=int(os.getenv("RAG_MIN_LEGAL_EVIDENCE", "2")),
            legal_retrieval_rpc_name=os.getenv("LEGAL_RETRIEVAL_RPC_NAME", "match_legal_docs_v6").strip(),
            legacy_legal_retrieval_rpc_name=os.getenv("LEGACY_LEGAL_RETRIEVAL_RPC_NAME", "match_legal_docs_v4").strip(),
            global_doc_top_k=int(os.getenv("GLOBAL_DOC_TOP_K", "5")),
            global_doc_score_threshold=float(os.getenv("GLOBAL_DOC_SCORE_THRESHOLD", "0.45")),
            rag_port=int(os.getenv("RAG_PORT", "8000")),
            rerank_model_name=os.getenv("RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3").strip(),
            rerank_candidate_count=int(os.getenv("RERANK_CANDIDATE_COUNT", "10")),
            rerank_final_top_k=int(os.getenv("RERANK_FINAL_TOP_K", "5")),
            chat_metrics_csv_enabled=_parse_env_bool("CHAT_METRICS_CSV_ENABLED", False),
            chat_metrics_csv_path=os.getenv(
                "CHAT_METRICS_CSV_PATH",
                "D:/Fishy/server/RAG/output/live_chat_metrics.csv",
            ).strip(),
        )

    @property
    def rerank_threshold(self) -> float:
        return self.rag_legal_score_threshold

    @property
    def min_legal_evidence(self) -> int:
        return self.rag_min_legal_evidence
