import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from sentence_transformers import CrossEncoder, SentenceTransformer
from supabase import Client

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.firecrawl_service import FirecrawlService
from services.trusted_web_cache_service import TrustedWebCacheService


logger = logging.getLogger("RETRIEVAL_SERVICE")

VEHICLE_TYPES = {"o_to", "xe_may", "xe_dap", "di_bo", "khac"}


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
        self.rerank_model_name = getattr(self.settings, "rerank_model_name", "BAAI/bge-reranker-v2-m3")
        self.rerank_candidate_count = int(getattr(self.settings, "rerank_candidate_count", 15))
        self.rerank_final_top_k = int(getattr(self.settings, "rerank_final_top_k", 5))
        self.reranker = CrossEncoder(self.rerank_model_name)

    def detect_vehicle_type(self, query: str) -> str:
        q = (query or "").strip().lower()

        if re.search(
            r"\b(ô tô|oto|o to|xe hơi|xe hoi|xe con|xe tải|xe tai|xe khách|xe khach|xe bán tải|xe ban tai|đầu kéo|dau keo|container|rơ moóc|ro mooc|sơ mi rơ moóc|so mi ro mooc)\b",
            q,
        ):
            return "o_to"

        if re.search(r"\b(xe máy|xe may|mô tô|mo to|moto|motor|xe gắn máy|xe gan may)\b", q):
            return "xe_may"

        if re.search(r"\b(xe đạp|xe dap|xe đạp điện|xe dap dien|xe thô sơ|xe tho so)\b", q):
            return "xe_dap"

        if re.search(r"\b(đi bộ|di bo|người đi bộ|nguoi di bo|bộ hành|bo hanh)\b", q):
            return "di_bo"

        return "khac"

    def extract_km(self, query: str) -> Optional[float]:
        pattern = (
            r"(\d+(?:[\.,]\d+)?)\s*(?:km/h|km|kmh|cây số|cay so|cây|cay)"
            r"|(?:quá|qua|lố|lo|chạy|chay|mức|muc|tốc độ|toc do)\s*(\d+(?:[\.,]\d+)?)"
        )
        match = re.search(pattern, query or "", re.IGNORECASE)
        if not match:
            return None

        raw_value = match.group(1) or match.group(2)
        if not raw_value:
            return None

        try:
            return float(raw_value.replace(",", "."))
        except ValueError:
            return None

    def search_legal_db(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        query_km = self.extract_km(question)
        vehicle_type = self.detect_vehicle_type(question)
        try:
            response = self.supabase.rpc(
                "match_legal_docs_v3",
                {
                    "vector_truy_van": query_vector,
                    "van_ban_truy_van": question,
                    "nguong_khop": self.settings.rag_legal_score_threshold,
                    "so_luong_ket_qua": self.rerank_candidate_count,
                    "so_km_truy_van": query_km,
                },
            ).execute()
            hits = self._map_legacy_legal_hits(response.data or [])
            logger.info(
                "legal retrieval rpc | function=match_legal_docs_v3 | results=%s | vehicle_type=%s | query_km=%s",
                len(hits),
                vehicle_type,
                query_km,
            )
            return hits
        except Exception as exc:
            logger.warning("match_legal_docs_v3 unavailable, fallback to hybrid_search_legal_sources: %s", exc)
            vector_literal = "[" + ",".join(f"{value:.10f}" for value in query_vector) + "]"
            legacy = self.supabase.rpc(
                "hybrid_search_legal_sources",
                {
                    "query_text": question,
                    "query_embedding": vector_literal,
                    "result_limit": self.rerank_candidate_count,
                },
            ).execute()
            hits = legacy.data or []
            logger.info("legal retrieval rpc | function=hybrid_search_legal_sources | results=%s", len(hits))
            return hits

    def search_trusted_cache(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        return self.trusted_cache_service.search_trusted_cache(
            question,
            query_vector,
            limit=self.rerank_candidate_count,
        )

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
        t0 = time.perf_counter()
        query_vector = self.embedding_model.encode("query: " + question, normalize_embeddings=True).tolist()
        detected_vehicle_type = self.detect_vehicle_type(question)

        legal_results = self.search_legal_db(question, query_vector)
        legal_ready, legal_above_threshold = self._meets_evidence_threshold(
            hits=legal_results,
            min_score=self.settings.rag_legal_score_threshold,
            min_evidence=self.settings.rag_min_legal_evidence,
        )
        logger.info(
            "retrieval legal | results=%s | above_threshold=%s | threshold=%.3f | vehicle_type=%s",
            len(legal_results),
            legal_above_threshold,
            self.settings.rag_legal_score_threshold,
            detected_vehicle_type,
        )

        trusted_results: List[Dict[str, Any]] = []
        firecrawl_called = False
        firecrawl_cached = 0
        searched_sources_count = 0
        scraped_urls_count = 0
        used_fallback = False

        if not legal_ready:
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

            if (not trusted_ready) and self.firecrawl_service.enabled and self.should_fallback_to_firecrawl(legal_results, trusted_results):
                cached_result = self.firecrawl_service.fetch_and_cache(question)
                trusted_results = self.search_trusted_cache(question, query_vector)

                firecrawl_called = True
                firecrawl_cached = len(cached_result["cached_rows"])
                searched_sources_count = cached_result["searched_sources_count"]
                scraped_urls_count = cached_result["scraped_urls_count"]
                used_fallback = True

                logger.info(
                    "retrieval final | firecrawl_called=%s | trusted_cache_results=%s",
                    True,
                    len(trusted_results),
                )

        t1 = time.perf_counter()
        candidate_results = self._merge_candidates(legal_results, trusted_results)
        reranked_results = self._rerank_results(question, candidate_results)
        t2 = time.perf_counter()

        retrieval_time_ms = round((t1 - t0) * 1000, 2)
        rerank_time_ms = round((t2 - t1) * 1000, 2)

        return {
            "candidate_results": candidate_results,
            "combined_results": reranked_results,
            "legal_results": legal_results,
            "trusted_cache_results": trusted_results,
            "firecrawl_called": firecrawl_called,
            "firecrawl_cached": firecrawl_cached,
            "searched_sources_count": searched_sources_count,
            "scraped_urls_count": scraped_urls_count,
            "used_fallback": used_fallback,
            "retrieval_time_ms": retrieval_time_ms,
            "rerank_time_ms": rerank_time_ms,
            "detected_vehicle_type": detected_vehicle_type,
        }

    def _dedupe_results(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped: List[Dict[str, Any]] = []

        for item in hits:
            key = (
                item.get("source_type"),
                item.get("primary_id"),
                (item.get("url") or "").strip(),
                (item.get("content") or "").strip()[:300],
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    def _merge_candidates(self, legal_results: List[Dict[str, Any]], trusted_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        combined = list(legal_results) + list(trusted_results)
        combined = self._dedupe_results(combined)
        combined.sort(
            key=lambda item: (
                0 if item.get("source_type") == "legal_db" else 1,
                -float(item.get("hybrid_score", 0.0)),
                -float(item.get("semantic_score", 0.0)),
            )
        )
        return combined[: self.rerank_candidate_count]

    def _vehicle_bonus(self, query_vehicle: str, doc_vehicle: str) -> float:
        if query_vehicle == "khac":
            return 0.0
        if doc_vehicle == query_vehicle:
            return 0.15
        if doc_vehicle == "khac":
            return 0.03
        return -0.05

    def _rerank_results(self, question: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not hits:
            return []

        query_vehicle = self.detect_vehicle_type(question)
        pairs = []
        for item in hits:
            content = (item.get("content") or "").strip()
            label = (item.get("label") or "").strip()
            text_for_rank = f"{label}\n{content}" if label else content
            pairs.append((question, text_for_rank))

        ce_scores = self.reranker.predict(pairs)

        reranked: List[Dict[str, Any]] = []
        for item, ce_score in zip(hits, ce_scores):
            doc_vehicle = self._normalize_vehicle_type(
                item.get("vehicle_type") or item.get("loai_phuong_tien")
            )
            vehicle_bonus = self._vehicle_bonus(query_vehicle, doc_vehicle)

            enriched = dict(item)
            enriched["vehicle_type"] = doc_vehicle
            enriched["cross_encoder_score"] = float(ce_score)
            enriched["vehicle_bonus"] = float(vehicle_bonus)
            enriched["final_rerank_score"] = float(ce_score) + float(vehicle_bonus)
            reranked.append(enriched)

        reranked.sort(
            key=lambda x: (
                x.get("final_rerank_score", 0.0),
                x.get("cross_encoder_score", 0.0),
                x.get("hybrid_score", 0.0),
            ),
            reverse=True,
        )
        return reranked[: self.rerank_final_top_k]

    def _meets_evidence_threshold(self, hits: List[Dict[str, Any]], min_score: float, min_evidence: int) -> Tuple[bool, int]:
        qualified_hits = [
            item for item in hits
            if float(item.get("hybrid_score", 0.0)) >= min_score
        ]
        return len(qualified_hits) >= min_evidence, len(qualified_hits)

    def _normalize_vehicle_type(self, value: Any) -> str:
        vehicle_type = str(value or "").strip().lower()
        return vehicle_type if vehicle_type in VEHICLE_TYPES else "khac"

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
                    "vehicle_type": "khac",
                    "loai_phuong_tien": "khac",
                    "lexical_score": score,
                    "semantic_score": score,
                    "hybrid_score": score,
                }
            )
        return hits
