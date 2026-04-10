import logging
from typing import Any, Dict, List, Tuple

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
        try:
            response = self.supabase.rpc(
                "match_legal_docs_v2",
                {
                    "vector_truy_van": query_vector,
                    "van_ban_truy_van": question,
                    "nguong_khop": self.settings.rag_legal_score_threshold,
                    "so_luong_ket_qua": 5,
                    "so_km_truy_van": None,
                },
            ).execute()
            hits = self._map_legacy_legal_hits(response.data or [])
            logger.info("legal retrieval rpc | function=match_legal_docs_v2 | results=%s", len(hits))
            return hits
        except Exception as exc:
            logger.warning("match_legal_docs_v2 unavailable, fallback to hybrid_search_legal_sources: %s", exc)
            vector_literal = "[" + ",".join(f"{value:.10f}" for value in query_vector) + "]"
            legacy = self.supabase.rpc(
                "hybrid_search_legal_sources",
                {
                    "query_text": question,
                    "query_embedding": vector_literal,
                    "result_limit": 5,
                },
            ).execute()
            hits = legacy.data or []
            logger.info("legal retrieval rpc | function=hybrid_search_legal_sources | results=%s", len(hits))
            return hits

    def search_trusted_cache(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        return self.trusted_cache_service.search_trusted_cache(question, query_vector, limit=5)

    def should_fallback_to_firecrawl(self, legal_results: List[Dict[str, Any]], trusted_results: List[Dict[str, Any]]) -> bool:
        legal_ready, _ = self._meets_evidence_threshold(
            hits=legal_results,
            min_score=self.settings.rag_legal_score_threshold,
            min_evidence=self.settings.rag_min_legal_evidence,
        )
        if legal_ready:
            return False

        trusted_ready, _ = self._meets_evidence_threshold(
            hits=trusted_results,
            min_score=self.settings.rag_trusted_score_threshold,
            min_evidence=self.settings.rag_min_trusted_evidence,
        )
        return not trusted_ready

    def retrieve_context(self, question: str) -> Dict[str, Any]:
        query_vector = self.embedding_model.encode("query: " + question, normalize_embeddings=True).tolist()
        legal_results = self.search_legal_db(question, query_vector)
        legal_ready, legal_above_threshold = self._meets_evidence_threshold(
            hits=legal_results,
            min_score=self.settings.rag_legal_score_threshold,
            min_evidence=self.settings.rag_min_legal_evidence,
        )
        logger.info(
            "retrieval legal | results=%s | above_threshold=%s | threshold=%.3f",
            len(legal_results),
            legal_above_threshold,
            self.settings.rag_legal_score_threshold,
        )

        if legal_ready:
            return {
                "combined_results": legal_results,
                "legal_results": legal_results,
                "trusted_cache_results": [],
                "firecrawl_called": False,
                "firecrawl_cached": 0,
                "searched_sources_count": 0,
                "scraped_urls_count": 0,
                "used_fallback": False,
            }

        trusted_results = self.search_trusted_cache(question, query_vector)
        trusted_ready, trusted_above_threshold = self._meets_evidence_threshold(
            hits=trusted_results,
            min_score=self.settings.rag_trusted_score_threshold,
            min_evidence=self.settings.rag_min_trusted_evidence,
        )
        logger.info(
            "retrieval trusted_cache | results=%s | above_threshold=%s | threshold=%.3f",
            len(trusted_results),
            trusted_above_threshold,
            self.settings.rag_trusted_score_threshold,
        )
        if trusted_ready:
            combined = self._merge_results(legal_results, trusted_results)
            return {
                "combined_results": combined,
                "legal_results": legal_results,
                "trusted_cache_results": trusted_results,
                "firecrawl_called": False,
                "firecrawl_cached": 0,
                "searched_sources_count": 0,
                "scraped_urls_count": 0,
                "used_fallback": False,
            }

        if not self.firecrawl_service.enabled or not self.should_fallback_to_firecrawl(legal_results, trusted_results):
            return {
                "combined_results": self._merge_results(legal_results, trusted_results),
                "legal_results": legal_results,
                "trusted_cache_results": trusted_results,
                "firecrawl_called": False,
                "firecrawl_cached": 0,
                "searched_sources_count": 0,
                "scraped_urls_count": 0,
                "used_fallback": False,
            }

        cached_result = self.firecrawl_service.fetch_and_cache(question)
        refreshed_trusted = self.search_trusted_cache(question, query_vector)
        logger.info(
            "retrieval final | firecrawl_called=%s | trusted_cache_results=%s",
            True,
            len(refreshed_trusted),
        )
        combined = self._merge_results(legal_results, refreshed_trusted)
        return {
            "combined_results": combined,
            "legal_results": legal_results,
            "trusted_cache_results": refreshed_trusted,
            "firecrawl_called": True,
            "firecrawl_cached": len(cached_result["cached_rows"]),
            "searched_sources_count": cached_result["searched_sources_count"],
            "scraped_urls_count": cached_result["scraped_urls_count"],
            "used_fallback": True,
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

    def _meets_evidence_threshold(self, hits: List[Dict[str, Any]], min_score: float, min_evidence: int) -> Tuple[bool, int]:
        qualified_hits = [
            item for item in hits
            if float(item.get("hybrid_score", 0.0)) >= min_score
        ]
        return len(qualified_hits) >= min_evidence, len(qualified_hits)

    def _map_legacy_legal_hits(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hits = []
        for item in rows:
            score = float(item.get("do_tuong_dong", 0.0))
            hits.append(
                {
                    "source_type": "legal_db",
                    "source_table": "noidung",
                    "primary_id": item.get("sothutund"),
                    "label": item.get("duong_dan_phan_cap") or item.get("sohieu") or "Legal DB",
                    "content": item.get("noidung", ""),
                    "url": None,
                    "lexical_score": score,
                    "semantic_score": score,
                    "hybrid_score": score,
                }
            )
        return hits
