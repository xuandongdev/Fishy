import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from sentence_transformers import CrossEncoder, SentenceTransformer
from supabase import Client

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.firecrawl_service import FirecrawlService
from services.legal_query_context import (
    build_effective_legal_question,
    detect_legal_action,
    detect_vehicle_type,
    extract_km,
    normalize_legal_text,
)
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
        self.rerank_model_name = getattr(self.settings, "rerank_model_name", "BAAI/bge-reranker-v2-m3")
        self.rerank_candidate_count = int(getattr(self.settings, "rerank_candidate_count", 15))
        self.rerank_final_top_k = int(getattr(self.settings, "rerank_final_top_k", 5))
        try:
            self.reranker: Optional[CrossEncoder] = CrossEncoder(self.rerank_model_name)
        except Exception as exc:
            logger.warning("cannot load CrossEncoder %s: %s", self.rerank_model_name, exc)
            self.reranker = None

    def detect_vehicle_type(self, query: str) -> str:
        return detect_vehicle_type(query)

    def extract_km(self, query: str) -> Optional[float]:
        return extract_km(query)

    def search_legal_db(
        self,
        question: str,
        query_vector: List[float],
        query_km: Optional[float] = None,
        query_vehicle_type: str = "khac",
    ) -> List[Dict[str, Any]]:
        if query_km is None:
            query_km = self.extract_km(question)
        if query_vehicle_type == "khac":
            query_vehicle_type = self.detect_vehicle_type(question)

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
            hits = self._map_legacy_legal_hits(response.data or [], query_vehicle_type=query_vehicle_type)
            logger.info(
                "legal retrieval rpc | function=match_legal_docs_v3 | results=%s | vehicle_type=%s | query_km=%s",
                len(hits),
                query_vehicle_type,
                query_km,
            )
            return hits
        except Exception as exc:
            logger.warning("match_legal_docs_v3 unavailable, returning empty legal hits: %s", exc)
            return []

    def retrieve_context(
        self,
        question: str,
        original_question: Optional[str] = None,
        effective_question: Optional[str] = None,
        query_vehicle_type: Optional[str] = None,
        query_km: Optional[float] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        effective_question = (effective_question or question or "").strip()
        original_question = (original_question or question or "").strip()

        if not effective_question and history:
            context = build_effective_legal_question(original_question, history)
            effective_question = str(context.get("effective_question") or original_question)
            query_vehicle_type = query_vehicle_type or str(context.get("vehicle_type") or "khac")
            query_km = query_km if query_km is not None else context.get("query_km")

        query_vehicle_type = query_vehicle_type or self.detect_vehicle_type(effective_question)
        if query_km is None:
            query_km = self.extract_km(effective_question)

        logger.info(
            "retrieval input | original_question=%s | effective_question=%s | vehicle_type=%s | query_km=%s",
            original_question[:200],
            effective_question[:200],
            query_vehicle_type,
            query_km,
        )

        query_vector = self.embedding_model.encode(
            "query: " + effective_question,
            normalize_embeddings=True,
        ).tolist()

        legal_results = self.search_legal_db(
            question=effective_question,
            query_vector=query_vector,
            query_km=query_km,
            query_vehicle_type=query_vehicle_type,
        )

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
            query_vehicle_type,
        )

        candidate_hits = list(legal_results)
        rerank_start = time.perf_counter()
        final_hits = self._rerank_results(
            question=effective_question,
            hits=candidate_hits,
            query_vehicle_type=query_vehicle_type,
            query_km=query_km,
        )
        rerank_time_ms = round((time.perf_counter() - rerank_start) * 1000, 2)
        retrieval_time_ms = round((time.perf_counter() - t0) * 1000, 2)

        trusted_results: List[Dict[str, Any]] = []
        firecrawl_called = False
        firecrawl_cached = 0
        searched_sources_count = 0
        scraped_urls_count = 0
        used_fallback = False

        if not final_hits and not legal_ready:
            used_fallback = True
            trusted_results = self._retrieve_trusted_fallback(effective_question)

        return {
            "legal_results": legal_results,
            "trusted_cache_results": trusted_results,
            "candidate_results": candidate_hits,
            "combined_results": final_hits if final_hits else trusted_results,
            "firecrawl_called": firecrawl_called,
            "firecrawl_cached": firecrawl_cached,
            "searched_sources_count": searched_sources_count,
            "scraped_urls_count": scraped_urls_count,
            "used_fallback": used_fallback,
            "detected_vehicle_type": query_vehicle_type,
            "query_km": query_km,
            "original_question": original_question,
            "effective_question": effective_question,
            "retrieval_time_ms": retrieval_time_ms,
            "rerank_time_ms": rerank_time_ms,
        }

    def _retrieve_trusted_fallback(self, question: str) -> List[Dict[str, Any]]:
        # Giữ minimal fallback để không phá flow hiện tại. Legal-first vẫn là mặc định.
        results: List[Dict[str, Any]] = []
        try:
            if hasattr(self.trusted_cache_service, "search_cache"):
                cache_hits = self.trusted_cache_service.search_cache(question) or []
                for item in cache_hits:
                    results.append(
                        {
                            "primary_id": item.get("primary_id") or item.get("id"),
                            "label": item.get("label") or item.get("title") or "Trusted cache",
                            "content": item.get("content") or item.get("snippet") or "",
                            "url": item.get("url"),
                            "source_type": "trusted_web_cache",
                            "vehicle_type": "khac",
                            "doc_vehicle_type": None,
                            "hybrid_score": float(item.get("score") or 0.0),
                            "cross_encoder_score": 0.0,
                            "vehicle_bonus": 0.0,
                            "final_rerank_score": float(item.get("score") or 0.0),
                            "min_km": None,
                            "max_km": None,
                        }
                    )
        except Exception as exc:
            logger.warning("trusted cache fallback failed: %s", exc)
        return results

    def _map_legacy_legal_hits(
        self,
        rows: List[Dict[str, Any]],
        query_vehicle_type: str,
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for row in rows:
            hit = {
                "primary_id": row.get("sothutund"),
                "label": row.get("duong_dan_phan_cap") or row.get("sohieu") or f"CAN_CU_{row.get('sothutund')}",
                "content": row.get("noidung") or "",
                "url": row.get("url"),
                "source_type": "legal_db",
                # Không còn cột loai_phuong_tien trong DB. vehicle_type dưới đây là metadata suy ra từ query.
                "vehicle_type": query_vehicle_type,
                "doc_vehicle_type": None,
                "hybrid_score": float(row.get("do_tuong_dong") or 0.0),
                "cross_encoder_score": 0.0,
                "vehicle_bonus": 0.0,
                "final_rerank_score": float(row.get("do_tuong_dong") or 0.0),
                "min_km": row.get("min_km"),
                "max_km": row.get("max_km"),
                "sohieu": row.get("sohieu"),
                "sothutund_cha": row.get("sothutund_cha"),
            }
            hits.append(hit)
        return hits

    def _meets_evidence_threshold(
        self,
        hits: List[Dict[str, Any]],
        min_score: float,
        min_evidence: int,
    ) -> Tuple[bool, int]:
        above_threshold = [item for item in hits if float(item.get("hybrid_score") or 0.0) >= min_score]
        return len(above_threshold) >= min_evidence, len(above_threshold)

    def _rerank_results(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        query_vehicle_type: str,
        query_km: Optional[float],
    ) -> List[Dict[str, Any]]:
        if not hits:
            return []

        query_action = detect_legal_action(question)
        pairs = []
        for item in hits:
            content = (item.get("content") or "").strip()
            label = (item.get("label") or "").strip()
            text_for_rank = f"{label}\n{content}" if label else content
            pairs.append((question, text_for_rank))

        if self.reranker is not None:
            try:
                ce_scores = self.reranker.predict(pairs)
            except Exception as exc:
                logger.warning("reranker predict failed: %s", exc)
                ce_scores = [0.0 for _ in pairs]
        else:
            ce_scores = [0.0 for _ in pairs]

        reranked: List[Dict[str, Any]] = []
        for idx, (item, ce_score) in enumerate(zip(hits, ce_scores), start=1):
            label = item.get("label") or ""
            content = item.get("content") or ""
            hybrid_score = float(item.get("hybrid_score") or 0.0)
            text = f"{label}\n{content}"
            vehicle_bonus = self._vehicle_text_bonus(query_vehicle_type, text)
            km_bonus = self._km_bonus(query_km, item.get("min_km"), item.get("max_km"), text)
            action_bonus = self._action_bonus(query_action, text)
            final_score = hybrid_score * 0.65 + float(ce_score) * 0.15 + vehicle_bonus + km_bonus + action_bonus

            enriched = dict(item)
            enriched["cross_encoder_score"] = float(ce_score)
            enriched["vehicle_bonus"] = float(vehicle_bonus)
            enriched["km_bonus"] = float(km_bonus)
            enriched["action_bonus"] = float(action_bonus)
            enriched["final_rerank_score"] = float(final_score)
            reranked.append(enriched)

            logger.info(
                "top hits | stage=candidate | rank=%s | label=%s | score=%.4f | ce=%.4f | final=%.4f | query_vehicle=%s | min_km=%s | max_km=%s",
                idx,
                label[:200],
                hybrid_score,
                float(ce_score),
                float(final_score),
                query_vehicle_type,
                item.get("min_km"),
                item.get("max_km"),
            )

        reranked.sort(key=lambda x: x.get("final_rerank_score") or 0.0, reverse=True)
        final_hits = reranked[: self.rerank_final_top_k]
        for idx, item in enumerate(final_hits, start=1):
            logger.info(
                "top hits | stage=reranked | rank=%s | label=%s | score=%.4f | ce=%.4f | final=%.4f | query_vehicle=%s | min_km=%s | max_km=%s",
                idx,
                (item.get("label") or "")[:200],
                float(item.get("hybrid_score") or 0.0),
                float(item.get("cross_encoder_score") or 0.0),
                float(item.get("final_rerank_score") or 0.0),
                query_vehicle_type,
                item.get("min_km"),
                item.get("max_km"),
            )
        return final_hits

    def _vehicle_text_bonus(self, query_vehicle_type: str, text: str) -> float:
        if query_vehicle_type == "khac":
            return 0.0
        normalized = normalize_legal_text(text)
        if query_vehicle_type == "xe_may" and re.search(r"\b(xe may|mo to|moto|xe gan may)\b", normalized):
            return 0.12
        if query_vehicle_type == "o_to" and re.search(r"\b(o to|oto|xe hoi|xe con|xe tai|xe khach)\b", normalized):
            return 0.12
        if query_vehicle_type == "xe_dap" and re.search(r"\b(xe dap|xe dap dien|xe tho so)\b", normalized):
            return 0.12
        if query_vehicle_type == "di_bo" and re.search(r"\b(di bo|nguoi di bo|bo hanh)\b", normalized):
            return 0.12
        return 0.0

    def _km_bonus(self, query_km: Optional[float], min_km: Any, max_km: Any, text: str) -> float:
        if query_km is None:
            return 0.0
        try:
            if min_km is not None and max_km is not None and float(min_km) <= float(query_km) <= float(max_km):
                return 0.20
        except Exception:
            pass
        normalized = normalize_legal_text(text)
        if re.search(r"\b(toc do|km/h|km)\b", normalized):
            return 0.05
        return 0.0

    def _action_bonus(self, query_action: Optional[str], text: str) -> float:
        if not query_action:
            return 0.0
        normalized = normalize_legal_text(text)
        if query_action == "vuot_den_do" and re.search(r"\b(den do|tin hieu)\b", normalized):
            return 0.12
        if query_action == "qua_toc_do" and re.search(r"\b(toc do|km/h|km)\b", normalized):
            return 0.12
        if query_action == "nong_do_con" and re.search(r"\b(nong do con|con|bia ruou)\b", normalized):
            return 0.12
        if query_action == "khong_doi_mu" and re.search(r"\b(mu bao hiem|doi mu)\b", normalized):
            return 0.12
        if query_action == "cho_qua_nguoi" and re.search(r"\b(cho qua|so nguoi)\b", normalized):
            return 0.12
        if query_action == "di_sai_lan" and re.search(r"\b(lan duong|phan duong)\b", normalized):
            return 0.12
        return 0.0
