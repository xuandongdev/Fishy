import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from sentence_transformers import CrossEncoder, SentenceTransformer
from supabase import Client

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.firecrawl_service import FirecrawlService
from services.legal_query_context import detect_legal_action, detect_vehicle_type, extract_km
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
        return detect_vehicle_type(query)

    def extract_km(self, query: str) -> Optional[float]:
        return extract_km(query)

    def search_legal_db(
        self,
        effective_question: str,
        query_vector: List[float],
        query_km: Optional[float],
        vehicle_type: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        rpc_name = "match_legal_docs_v3"
        payload = {
            "vector_truy_van": query_vector,
            "van_ban_truy_van": effective_question,
            "nguong_khop": self.settings.rag_legal_score_threshold,
            "so_luong_ket_qua": self.rerank_candidate_count,
            "so_km_truy_van": query_km,
        }
        if vehicle_type != "khac":
            payload["p_loai_phuong_tien_truy_van"] = vehicle_type

        try:
            response = self.supabase.rpc(rpc_name, payload).execute()
        except Exception as exc:
            if "p_loai_phuong_tien_truy_van" in payload:
                logger.warning(
                    "legal retrieval rpc retry without vehicle param | function=%s | vehicle_type=%s | error=%s",
                    rpc_name,
                    vehicle_type,
                    exc,
                )
                payload.pop("p_loai_phuong_tien_truy_van", None)
                response = self.supabase.rpc(rpc_name, payload).execute()
            else:
                logger.warning("match_legal_docs_v3 unavailable, fallback to hybrid_search_legal_sources: %s", exc)
                vector_literal = "[" + ",".join(f"{value:.10f}" for value in query_vector) + "]"
                rpc_name = "hybrid_search_legal_sources"
                response = self.supabase.rpc(
                    rpc_name,
                    {
                        "query_text": effective_question,
                        "query_embedding": vector_literal,
                        "result_limit": self.rerank_candidate_count,
                    },
                ).execute()

        hits = self._map_legal_hits(response.data or [])
        logger.info(
            "legal retrieval rpc | function=%s | results=%s | vehicle_type=%s | query_km=%s",
            rpc_name,
            len(hits),
            vehicle_type,
            query_km,
        )
        return hits, rpc_name

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

    def retrieve_context(
        self,
        effective_question: str,
        *,
        original_question: Optional[str] = None,
        detected_vehicle_type: Optional[str] = None,
        query_km: Optional[float] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        original_question = original_question or effective_question
        detected_vehicle_type = detected_vehicle_type or self.detect_vehicle_type(effective_question)
        query_km = query_km if query_km is not None else self.extract_km(effective_question)

        logger.info(
            "retrieval input | original_question=%s | effective_question=%s | vehicle_type=%s | query_km=%s",
            original_question[:200],
            effective_question[:200],
            detected_vehicle_type,
            query_km,
        )

        query_vector = self.embedding_model.encode("query: " + effective_question, normalize_embeddings=True).tolist()
        legal_results, rpc_name = self.search_legal_db(
            effective_question=effective_question,
            query_vector=query_vector,
            query_km=query_km,
            vehicle_type=detected_vehicle_type,
        )
        legal_ready, legal_above_threshold = self._meets_evidence_threshold(
            hits=legal_results,
            min_score=self.settings.rag_legal_score_threshold,
            min_evidence=self.settings.rag_min_legal_evidence,
        )
        logger.info(
            "retrieval legal | results=%s | above_threshold=%s | threshold=%.3f | vehicle_type=%s | query_km=%s",
            len(legal_results),
            legal_above_threshold,
            self.settings.rag_legal_score_threshold,
            detected_vehicle_type,
            query_km,
        )

        trusted_results: List[Dict[str, Any]] = []
        firecrawl_called = False
        firecrawl_cached = 0
        searched_sources_count = 0
        scraped_urls_count = 0
        used_fallback = False

        candidate_results = list(legal_results)
        reranked_results = self._rank_legal_hits(
            effective_question=effective_question,
            hits=legal_results,
            query_km=query_km,
            vehicle_type=detected_vehicle_type,
        )

        if not legal_ready:
            trusted_results = self.search_trusted_cache(effective_question, query_vector)
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
                cached_result = self.firecrawl_service.fetch_and_cache(effective_question)
                trusted_results = self.search_trusted_cache(effective_question, query_vector)
                firecrawl_called = True
                firecrawl_cached = len(cached_result["cached_rows"])
                searched_sources_count = cached_result["searched_sources_count"]
                scraped_urls_count = cached_result["scraped_urls_count"]
                used_fallback = True

            candidate_results = self._merge_candidates(legal_results, trusted_results)
            reranked_results = self._rank_combined_hits(
                effective_question=effective_question,
                hits=candidate_results,
                query_km=query_km,
                vehicle_type=detected_vehicle_type,
            )

        t1 = time.perf_counter()
        self._log_top_hits("candidate", candidate_results, query_km=query_km)
        self._log_top_hits("reranked", reranked_results, query_km=query_km)
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
            "query_km": query_km,
            "rpc_function_name": rpc_name,
            "original_question": original_question,
            "effective_question": effective_question,
        }

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

    def _rank_legal_hits(
        self,
        *,
        effective_question: str,
        hits: List[Dict[str, Any]],
        query_km: Optional[float],
        vehicle_type: str,
    ) -> List[Dict[str, Any]]:
        if not hits:
            return []

        action = detect_legal_action(effective_question)
        ce_scores = self._predict_cross_scores(effective_question, hits)
        ranked: List[Dict[str, Any]] = []
        for item, ce_score in zip(hits, ce_scores):
            hybrid_score = float(item.get("hybrid_score", 0.0))
            doc_vehicle = self._normalize_vehicle_type(item.get("vehicle_type") or item.get("loai_phuong_tien"))
            vehicle_bonus = self._vehicle_bonus(vehicle_type, doc_vehicle)
            km_bonus = self._km_bonus(query_km, item.get("min_km"), item.get("max_km"))
            action_bonus = self._action_bonus(action, item)
            final_score = hybrid_score + vehicle_bonus + km_bonus + action_bonus + (0.05 * ce_score)

            enriched = dict(item)
            enriched["vehicle_type"] = doc_vehicle
            enriched["cross_encoder_score"] = float(ce_score)
            enriched["vehicle_bonus"] = float(vehicle_bonus)
            enriched["km_bonus"] = float(km_bonus)
            enriched["action_bonus"] = float(action_bonus)
            enriched["final_rerank_score"] = float(final_score)
            ranked.append(enriched)

        ranked.sort(
            key=lambda item: (
                item.get("final_rerank_score", 0.0),
                item.get("hybrid_score", 0.0),
            ),
            reverse=True,
        )
        return ranked[: self.rerank_final_top_k]

    def _rank_combined_hits(
        self,
        *,
        effective_question: str,
        hits: List[Dict[str, Any]],
        query_km: Optional[float],
        vehicle_type: str,
    ) -> List[Dict[str, Any]]:
        legal_hits = [item for item in hits if item.get("source_type") == "legal_db"]
        trusted_hits = [item for item in hits if item.get("source_type") != "legal_db"]

        ranked_legal = self._rank_legal_hits(
            effective_question=effective_question,
            hits=legal_hits,
            query_km=query_km,
            vehicle_type=vehicle_type,
        )

        if not trusted_hits:
            return ranked_legal

        ce_scores = self._predict_cross_scores(effective_question, trusted_hits)
        ranked_trusted: List[Dict[str, Any]] = []
        for item, ce_score in zip(trusted_hits, ce_scores):
            enriched = dict(item)
            enriched["cross_encoder_score"] = float(ce_score)
            enriched["vehicle_bonus"] = 0.0
            enriched["km_bonus"] = 0.0
            enriched["action_bonus"] = 0.0
            enriched["final_rerank_score"] = float(item.get("hybrid_score", 0.0)) + (0.15 * float(ce_score))
            ranked_trusted.append(enriched)

        ranked_trusted.sort(key=lambda item: item.get("final_rerank_score", 0.0), reverse=True)
        combined = ranked_legal + ranked_trusted
        combined.sort(
            key=lambda item: (
                0 if item.get("source_type") == "legal_db" else 1,
                -float(item.get("final_rerank_score", 0.0)),
                -float(item.get("hybrid_score", 0.0)),
            )
        )
        return combined[: self.rerank_final_top_k]

    def _predict_cross_scores(self, effective_question: str, hits: List[Dict[str, Any]]) -> List[float]:
        if not hits:
            return []
        pairs = []
        for item in hits:
            label = (item.get("label") or "").strip()
            content = (item.get("content") or "").strip()
            pairs.append((effective_question, f"{label}\n{content}" if label else content))
        return [float(score) for score in self.reranker.predict(pairs)]

    def _vehicle_bonus(self, query_vehicle: str, doc_vehicle: str) -> float:
        if query_vehicle == "khac":
            return 0.0
        if doc_vehicle == query_vehicle:
            return 0.25
        if doc_vehicle == "khac":
            return -0.03
        return -0.12

    def _km_bonus(self, query_km: Optional[float], min_km_raw: Any, max_km_raw: Any) -> float:
        if query_km is None:
            return 0.0

        min_km = self._coerce_float(min_km_raw)
        max_km = self._coerce_float(max_km_raw)
        if min_km is None and max_km is None:
            return -0.12

        lower_bound = min_km if min_km is not None else -math.inf
        upper_bound = max_km if max_km is not None else math.inf
        if lower_bound <= query_km <= upper_bound:
            return 0.35

        if min_km is not None and query_km < min_km:
            return max(-0.25, -0.02 * (min_km - query_km))
        if max_km is not None and query_km > max_km:
            return max(-0.25, -0.02 * (query_km - max_km))
        return -0.1

    def _action_bonus(self, action: Optional[str], item: Dict[str, Any]) -> float:
        if not action:
            return 0.0

        label = str(item.get("label") or "").lower()
        content = str(item.get("content") or "").lower()
        haystack = f"{label}\n{content}"

        if action == "vuot den do":
            return 0.18 if "den do" in haystack else -0.04
        if action == "chay qua toc do":
            if item.get("min_km") is not None or item.get("max_km") is not None:
                return 0.2
            return 0.12 if "toc do" in haystack else -0.06
        if action == "dua xe":
            return 0.18 if "dua xe" in haystack else -0.04
        if action == "vi pham nong do con":
            return 0.18 if "nong do con" in haystack else -0.04
        if action == "cho qua so nguoi quy dinh":
            return 0.14 if "cho" in haystack else -0.04
        return 0.0

    def _meets_evidence_threshold(self, hits: List[Dict[str, Any]], min_score: float, min_evidence: int) -> Tuple[bool, int]:
        qualified_hits = [item for item in hits if float(item.get("hybrid_score", 0.0)) >= min_score]
        return len(qualified_hits) >= min_evidence, len(qualified_hits)

    def _normalize_vehicle_type(self, value: Any) -> str:
        vehicle_type = str(value or "").strip().lower()
        return vehicle_type if vehicle_type in VEHICLE_TYPES else "khac"

    def _map_legal_hits(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for item in rows:
            score = self._coerce_float(
                item.get("do_tuong_dong")
                or item.get("hybrid_score")
                or item.get("semantic_score")
                or item.get("score")
            ) or 0.0
            loai_phuong_tien = (
                item.get("loai_phuong_tien")
                or item.get("vehicle_type")
                or item.get("p_loai_phuong_tien")
                or "khac"
            )
            hits.append(
                {
                    "source_type": "legal_db",
                    "source_table": item.get("source_table") or "noidung",
                    "primary_id": item.get("sothutund") or item.get("id"),
                    "label": item.get("duong_dan_phan_cap") or item.get("path") or item.get("sohieu") or "Legal DB",
                    "content": item.get("noidung", ""),
                    "url": None,
                    "vehicle_type": self._normalize_vehicle_type(loai_phuong_tien),
                    "loai_phuong_tien": self._normalize_vehicle_type(loai_phuong_tien),
                    "min_km": self._coerce_float(item.get("min_km") or item.get("km_tu")),
                    "max_km": self._coerce_float(item.get("max_km") or item.get("km_den")),
                    "sohieu": item.get("sohieu"),
                    "duong_dan_phan_cap": item.get("duong_dan_phan_cap"),
                    "sothutund_cha": item.get("sothutund_cha"),
                    "lexical_score": score,
                    "semantic_score": score,
                    "hybrid_score": score,
                }
            )
        return hits

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _log_top_hits(self, stage: str, hits: List[Dict[str, Any]], query_km: Optional[float]) -> None:
        if not hits:
            logger.info("top hits | stage=%s | empty | query_km=%s", stage, query_km)
            return

        for index, item in enumerate(hits[:5], start=1):
            logger.info(
                "top hits | stage=%s | rank=%s | label=%s | hybrid=%.4f | rerank=%.4f | final=%.4f | vehicle=%s | min_km=%s | max_km=%s",
                stage,
                index,
                (item.get("label") or "")[:160],
                float(item.get("hybrid_score", 0.0)),
                float(item.get("cross_encoder_score", 0.0)),
                float(item.get("final_rerank_score", item.get("hybrid_score", 0.0))),
                item.get("vehicle_type") or item.get("loai_phuong_tien"),
                item.get("min_km"),
                item.get("max_km"),
            )
