import logging
from typing import Any, Dict, List

from sentence_transformers import SentenceTransformer
from supabase import Client

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.firecrawl_service import FirecrawlService
from services.trusted_web_cache_service import TrustedWebCacheService


logger = logging.getLogger("RETRIEVAL_SERVICE")


class RetrievalService:
    def __init__(
        self,
        supabase: Client,
        embedding_model: SentenceTransformer,
        settings: RAGSettings,
        trusted_cache_service: TrustedWebCacheService,
        firecrawl_service: FirecrawlService,
        answer_service: AnswerService,
    ) -> None:
        self.supabase = supabase
        self.embedding_model = embedding_model
        self.settings = settings
        self.trusted_cache_service = trusted_cache_service
        self.firecrawl_service = firecrawl_service
        self.answer_service = answer_service

    def search_legal_db(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        vector_literal = "[" + ",".join(f"{value:.10f}" for value in query_vector) + "]"
        try:
            response = self.supabase.rpc(
                "hybrid_search_legal_sources",
                {
                    "query_text": question,
                    "query_embedding": vector_literal,
                    "result_limit": 5,
                },
            ).execute()
            return response.data or []
        except Exception as exc:
            logger.warning("legal hybrid rpc unavailable, fallback to match_legal_docs_v2: %s", exc)
            legacy = self.supabase.rpc(
                "match_legal_docs_v2",
                {
                    "vector_truy_van": query_vector,
                    "van_ban_truy_van": question,
                    "nguong_khop": self.settings.rerank_threshold,
                    "so_luong_ket_qua": 5,
                    "so_km_truy_van": None,
                },
            ).execute()
            hits = []
            for item in legacy.data or []:
                hits.append(
                    {
                        "source_type": "legal_db",
                        "source_table": "noidung",
                        "primary_id": item.get("sothutund"),
                        "label": item.get("duong_dan_phan_cap") or item.get("sohieu") or "Legal DB",
                        "content": item.get("noidung", ""),
                        "url": None,
                        "lexical_score": float(item.get("do_tuong_dong", 0.0)),
                        "semantic_score": float(item.get("do_tuong_dong", 0.0)),
                        "hybrid_score": float(item.get("do_tuong_dong", 0.0)),
                    }
                )
            return hits

    def search_trusted_cache(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        return self.trusted_cache_service.search_trusted_cache(question, query_vector, limit=5)

    def should_fallback_to_firecrawl(self, legal_results: List[Dict[str, Any]], trusted_results: List[Dict[str, Any]]) -> bool:
        legal_eval = self.answer_service.assess_context(
            question="legal_check",
            hits=legal_results,
            min_score=self.settings.rerank_threshold,
            min_evidence=self.settings.min_legal_evidence,
        )
        if not legal_eval.get("insufficient_context", True):
            return False

        trusted_eval = self.answer_service.assess_context(
            question="trusted_check",
            hits=trusted_results,
            min_score=self.settings.trusted_threshold,
            min_evidence=self.settings.min_trusted_evidence,
        )
        return bool(trusted_eval.get("insufficient_context", True))

    def retrieve_context(self, question: str) -> Dict[str, Any]:
        query_vector = self.embedding_model.encode("query: " + question, normalize_embeddings=True).tolist()
        legal_results = self.search_legal_db(question, query_vector)

        legal_eval = self.answer_service.assess_context(
            question=question,
            hits=legal_results,
            min_score=self.settings.rerank_threshold,
            min_evidence=self.settings.min_legal_evidence,
        )
        if not legal_eval.get("insufficient_context", True):
            return {
                "combined_results": legal_results,
                "legal_results": legal_results,
                "trusted_cache_results": [],
                "firecrawl_called": False,
                "firecrawl_cached": 0,
                "used_fallback": False,
            }

        trusted_results = self.search_trusted_cache(question, query_vector)
        trusted_eval = self.answer_service.assess_context(
            question=question,
            hits=trusted_results,
            min_score=self.settings.trusted_threshold,
            min_evidence=self.settings.min_trusted_evidence,
        )
        if not trusted_eval.get("insufficient_context", True):
            combined = self._merge_results(legal_results, trusted_results)
            return {
                "combined_results": combined,
                "legal_results": legal_results,
                "trusted_cache_results": trusted_results,
                "firecrawl_called": False,
                "firecrawl_cached": 0,
                "used_fallback": False,
            }

        cached_rows = self.firecrawl_service.fetch_and_cache(question)
        refreshed_trusted = self.search_trusted_cache(question, query_vector)
        combined = self._merge_results(legal_results, refreshed_trusted)
        return {
            "combined_results": combined,
            "legal_results": legal_results,
            "trusted_cache_results": refreshed_trusted,
            "firecrawl_called": self.firecrawl_service.enabled,
            "firecrawl_cached": len(cached_rows),
            "used_fallback": self.firecrawl_service.enabled,
        }

    def _merge_results(self, legal_results: List[Dict[str, Any]], trusted_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        combined = list(legal_results) + list(trusted_results)
        combined.sort(
            key=lambda item: (
                0 if item.get("source_type") == "legal_db" else 1,
                -float(item.get("hybrid_score", 0.0)),
            )
        )
        return combined[:6]
