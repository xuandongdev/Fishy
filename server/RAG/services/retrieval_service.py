import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from sentence_transformers import CrossEncoder, SentenceTransformer
from supabase import Client

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.firecrawl_service import FirecrawlService
from services.global_doc_service import GlobalDocService
from services.legal_query_context import (
    build_effective_legal_question,
    detect_legal_action,
    detect_vehicle_type,
    extract_km,
    normalize_legal_text,
)
from services.session_doc_service import SessionDocService
from services.trusted_web_cache_service import TrustedWebCacheService


logger = logging.getLogger("RETRIEVAL_SERVICE")
EXACT_LEGAL_INTENTS = {"muc_phat", "can_cu_phap_ly", "tuoc_gplx", "tam_giu_phuong_tien"}


class RetrievalService:
    def __init__(
        self,
        supabase: Client,
        embedding_model: SentenceTransformer,
        settings: RAGSettings,
        trusted_cache_service: TrustedWebCacheService,
        firecrawl_service: FirecrawlService,
        session_doc_service: SessionDocService,
        global_doc_service: GlobalDocService,
        answer_service: AnswerService,
    ) -> None:
        self.supabase = supabase
        self.embedding_model = embedding_model
        self.settings = settings
        self.trusted_cache_service = trusted_cache_service
        self.firecrawl_service = firecrawl_service
        self.session_doc_service = session_doc_service
        self.global_doc_service = global_doc_service
        self.answer_service = answer_service
        self.rerank_model_name = getattr(self.settings, "rerank_model_name", "BAAI/bge-reranker-v2-m3")
        self.rerank_candidate_count = int(getattr(self.settings, "rerank_candidate_count", 10))
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

    def has_session_docs(self, session_id: Optional[str]) -> bool:
        return False

    def has_global_docs(self) -> bool:
        try:
            return self.global_doc_service.has_global_docs()
        except Exception as exc:
            logger.warning("global doc presence check failed | reason=%s", exc)
            return False

    def search_legal_db(
        self,
        question: str,
        query_vector: List[float],
        query_km: Optional[float] = None,
        query_vehicle_type: str = "khac",
    ) -> Dict[str, Any]:
        if query_km is None:
            query_km = self.extract_km(question)
        if query_vehicle_type == "khac":
            query_vehicle_type = self.detect_vehicle_type(question)

        rpc_payload = {
            "vector_truy_van": query_vector,
            "van_ban_truy_van": question,
            "nguong_khop": self.settings.rag_legal_score_threshold,
            "so_luong_ket_qua": self.rerank_candidate_count,
            "so_km_truy_van": query_km,
        }

        try:
            response = self.supabase.rpc("match_legal_docs_v4", rpc_payload).execute()
            hits = self._map_legal_hits(response.data or [], query_vehicle_type=query_vehicle_type)
            logger.info(
                "legal retrieval rpc | rpc_selected=v4 | results=%s | vehicle_type=%s | query_km=%s",
                len(hits),
                query_vehicle_type,
                query_km,
            )
            return {
                "hits": hits,
                "legal_db_unavailable": False,
                "rpc_selected": "v4",
                "v4_error_reason": None,
            }
        except Exception as exc:
            logger.warning("legal retrieval rpc failed | rpc_selected=v4 | v4_error_reason=%s", exc)
            return {
                "hits": [],
                "legal_db_unavailable": True,
                "rpc_selected": "v4",
                "v4_error_reason": str(exc),
            }

    def search_trusted_cache(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        try:
            return self.trusted_cache_service.search_trusted_cache(
                question=question,
                query_vector=query_vector,
                limit=self.settings.rerank_final_top_k,
            )
        except Exception as exc:
            logger.warning("trusted cache search failed: %s", exc)
            return []

    def search_global_docs(self, question: str, query_vector: List[float]) -> List[Dict[str, Any]]:
        try:
            return self.global_doc_service.qdrant_service.search_global_docs(
                question=question,
                query_vector=query_vector,
                limit=self.settings.global_doc_top_k,
            )
        except Exception as exc:
            logger.warning("global doc search failed: %s", exc)
            return []

    def retrieve_context(
        self,
        question: str,
        original_question: Optional[str] = None,
        effective_question: Optional[str] = None,
        query_vehicle_type: Optional[str] = None,
        query_km: Optional[float] = None,
        intent: Optional[str] = None,
        action: Optional[str] = None,
        rewrite_confidence: Optional[float] = None,
        session_id: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        skip_session_docs: bool = False,
        skip_global_docs: bool = False,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        effective_question = (effective_question or question or "").strip()
        original_question = (original_question or question or "").strip()

        if not effective_question and history:
            context = build_effective_legal_question(original_question, history)
            effective_question = str(context.get("effective_question") or original_question)
            query_vehicle_type = query_vehicle_type or str(context.get("vehicle_type") or "khac")
            query_km = query_km if query_km is not None else context.get("query_km")
            intent = intent or str(context.get("intent") or "followup_khong_ro")
            action = action or str(context.get("action") or "")
            rewrite_confidence = rewrite_confidence if rewrite_confidence is not None else float(
                context.get("rewrite_confidence") or 0.0
            )

        query_vehicle_type = query_vehicle_type or self.detect_vehicle_type(effective_question)
        if query_km is None:
            query_km = self.extract_km(effective_question)
        exact_legal_query = self._is_exact_legal_query(intent=intent, action=action, query_km=query_km)
        query_kind = "exact_legal_query" if exact_legal_query else "general_legal_query"

        logger.info(
            "retrieval input | original_question=%s | effective_question=%s | intent=%s | action=%s | vehicle_type=%s | query_km=%s | rewrite_confidence=%s | query_kind=%s | session_id=%s",
            original_question[:200],
            effective_question[:200],
            intent,
            action,
            query_vehicle_type,
            query_km,
            rewrite_confidence,
            query_kind,
            session_id,
        )

        query_vector = self.embedding_model.encode("query: " + effective_question, normalize_embeddings=True).tolist()

        global_doc_hits: List[Dict[str, Any]] = []
        global_doc_ready = False
        global_doc_top_score = 0.0
        used_global_docs = False
        session_doc_hits: List[Dict[str, Any]] = []
        session_doc_top_score = 0.0
        used_session_docs = False
        session_docs_available = False
        fallback_to_legal_db = False
        fallback_to_trusted_cache = False
        fallback_to_firecrawl = False
        if not skip_global_docs:
            global_docs_available = self.has_global_docs()
            logger.info("global doc availability | has_global_docs=%s", global_docs_available)
            if global_docs_available:
                global_doc_hits = self.search_global_docs(effective_question, query_vector)
                if global_doc_hits:
                    global_doc_top_score = float(
                        global_doc_hits[0].get("final_rerank_score")
                        or global_doc_hits[0].get("hybrid_score")
                        or 0.0
                    )
                    global_doc_ready = self._global_docs_sufficient(
                        question=effective_question,
                        hits=global_doc_hits,
                        intent=intent,
                        action=action,
                        query_vehicle_type=query_vehicle_type,
                        query_km=query_km,
                    )
                logger.info(
                    "global doc retrieval | global_doc_hits=%s | global_doc_top_score=%s | global_doc_used=%s | fallback_to_rpc_v4=%s",
                    len(global_doc_hits),
                    round(global_doc_top_score, 4),
                    global_doc_ready,
                    not global_doc_ready,
                )
                if global_doc_ready:
                    used_global_docs = True
                else:
                    fallback_to_legal_db = True

        legal_results: List[Dict[str, Any]] = []
        candidate_hits: List[Dict[str, Any]] = []
        final_hits: List[Dict[str, Any]] = global_doc_hits if used_global_docs else []
        legal_db_unavailable = False
        v4_error_reason = None
        km_match_count = 0
        intent_match_count = 0
        topic_mismatch = False
        trusted_results_before_firecrawl: List[Dict[str, Any]] = []
        trusted_results: List[Dict[str, Any]] = []
        firecrawl_called = False
        firecrawl_cached = 0
        searched_sources_count = 0
        scraped_urls_count = 0
        trusted_intent_match_count = 0
        trusted_topic_mismatch = False
        used_fallback = False
        fallback_reason = ""

        if not used_global_docs and not used_session_docs:
            legal_search = self.search_legal_db(
                question=effective_question,
                query_vector=query_vector,
                query_km=query_km,
                query_vehicle_type=query_vehicle_type,
            )
            legal_results = legal_search["hits"]
            legal_db_unavailable = bool(legal_search["legal_db_unavailable"])
            v4_error_reason = legal_search["v4_error_reason"]
            candidate_hits = list(legal_results)

            legal_ready, legal_above_threshold = self._meets_evidence_threshold(
                hits=legal_results,
                min_score=self.settings.rag_legal_score_threshold,
                min_evidence=self.settings.rag_min_legal_evidence,
            )
            km_match_count = sum(1 for item in legal_results if item.get("km_phu_hop") is True)
            intent_match_count = self._intent_match_count(
                hits=legal_results,
                query_vehicle_type=query_vehicle_type,
                action=action,
                query_km=query_km,
            )
            topic_mismatch = bool(legal_results) and intent_match_count == 0
            logger.info(
                "retrieval legal | results=%s | above_threshold=%s | km_match_hits=%s | intent_match=%s | topic_mismatch=%s",
                len(legal_results),
                legal_above_threshold,
                km_match_count,
                intent_match_count,
                topic_mismatch,
            )

            rerank_start = time.perf_counter()
            final_hits = self._rerank_results(
                question=effective_question,
                hits=candidate_hits,
                query_vehicle_type=query_vehicle_type,
                query_km=query_km,
                action=action,
            )
            rerank_time_ms = round((time.perf_counter() - rerank_start) * 1000, 2)

            should_use_fallback = False
            if legal_db_unavailable:
                should_use_fallback = True
                used_fallback = True
                fallback_reason = "legal_db_unavailable"
            elif len(final_hits) < self.settings.rag_min_legal_evidence:
                should_use_fallback = True
                used_fallback = True
                fallback_reason = "too_few_legal_hits"
            elif topic_mismatch:
                should_use_fallback = True
                used_fallback = True
                fallback_reason = "topic_mismatch"
            elif query_km is not None and action == "qua_toc_do" and km_match_count == 0:
                should_use_fallback = True
                used_fallback = True
                fallback_reason = "missing_km_match"

            if should_use_fallback:
                trusted_results_before_firecrawl = self.search_trusted_cache(effective_question, query_vector)
                trusted_results = trusted_results_before_firecrawl
                trusted_ready, _ = self._meets_evidence_threshold(
                    hits=trusted_results_before_firecrawl,
                    min_score=self.settings.rag_trusted_score_threshold,
                    min_evidence=self.settings.rag_min_trusted_evidence,
                )
                trusted_intent_match_count, trusted_topic_mismatch = self._evaluate_trusted_hits(
                    question=effective_question,
                    hits=trusted_results_before_firecrawl,
                    query_vehicle_type=query_vehicle_type,
                    intent=intent,
                    action=action,
                    query_km=query_km,
                )
                logger.info(
                    "retrieval trusted cache | trusted_before=%s | trusted_intent_match_count=%s | trusted_topic_mismatch=%s",
                    len(trusted_results_before_firecrawl),
                    trusted_intent_match_count,
                    trusted_topic_mismatch,
                )
                should_call_firecrawl = (
                    not trusted_ready
                    or not trusted_results_before_firecrawl
                    or trusted_topic_mismatch
                    or trusted_intent_match_count == 0
                )
                if should_call_firecrawl and self.firecrawl_service.enabled:
                    firecrawl_called = True
                    firecrawl_result = self.firecrawl_service.fetch_and_cache(effective_question)
                    firecrawl_cached = len(firecrawl_result.get("cached_rows") or [])
                    searched_sources_count = int(firecrawl_result.get("searched_sources_count") or 0)
                    scraped_urls_count = int(firecrawl_result.get("scraped_urls_count") or 0)
                    trusted_results = self.search_trusted_cache(effective_question, query_vector)
                    fallback_to_firecrawl = True
                if trusted_results:
                    final_hits = self._rerank_results(
                        question=effective_question,
                        hits=trusted_results,
                        query_vehicle_type=query_vehicle_type,
                        query_km=query_km,
                        action=action,
                    )
                    fallback_to_trusted_cache = True
            else:
                logger.info("retrieval trusted cache | skipped=True | reason=legal_path_sufficient")
        else:
            rerank_time_ms = 0.0

        retrieval_time_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "retrieval fallback summary | global_doc_hits=%s | has_session_docs=%s | session_doc_hits=%s | legal_results=%s | trusted_before=%s | trusted_after=%s | used_global_docs=%s | used_session_docs=%s | fallback_to_legal_db=%s | fallback_to_trusted_cache=%s | fallback_to_firecrawl=%s | used_fallback=%s | firecrawl_called=%s | final_fallback_reason=%s",
            len(global_doc_hits),
            session_docs_available,
            len(session_doc_hits),
            len(legal_results),
            len(trusted_results_before_firecrawl),
            len(trusted_results),
            used_global_docs,
            used_session_docs,
            fallback_to_legal_db,
            fallback_to_trusted_cache,
            fallback_to_firecrawl,
            used_fallback,
            firecrawl_called,
            fallback_reason or "none",
        )

        return {
            "global_doc_results": global_doc_hits,
            "global_doc_hits": len(global_doc_hits),
            "global_doc_top_score": global_doc_top_score,
            "used_global_docs": used_global_docs,
            "session_doc_results": session_doc_hits,
            "session_doc_hits": len(session_doc_hits),
            "session_doc_source_count": len({item.get("file_id") for item in session_doc_hits if item.get("file_id")}),
            "session_doc_top_score": session_doc_top_score,
            "used_session_docs": used_session_docs,
            "fallback_to_legal_db": fallback_to_legal_db,
            "fallback_to_trusted_cache": fallback_to_trusted_cache,
            "fallback_to_firecrawl": fallback_to_firecrawl,
            "legal_results": legal_results,
            "trusted_cache_results": trusted_results,
            "candidate_results": candidate_hits,
            "combined_results": final_hits,
            "firecrawl_called": firecrawl_called,
            "firecrawl_cached": firecrawl_cached,
            "searched_sources_count": searched_sources_count,
            "scraped_urls_count": scraped_urls_count,
            "used_fallback": used_fallback,
            "legal_db_unavailable": legal_db_unavailable,
            "rpc_selected": "v4",
            "v4_error_reason": v4_error_reason,
            "detected_vehicle_type": query_vehicle_type,
            "query_km": query_km,
            "intent": intent,
            "action": action,
            "rewrite_confidence": rewrite_confidence,
            "exact_legal_query": exact_legal_query,
            "km_match_count": km_match_count,
            "intent_match_count": intent_match_count,
            "topic_mismatch": topic_mismatch,
            "trusted_intent_match_count": trusted_intent_match_count,
            "trusted_topic_mismatch": trusted_topic_mismatch,
            "final_fallback_reason": fallback_reason,
            "original_question": original_question,
            "effective_question": effective_question,
            "retrieval_time_ms": retrieval_time_ms,
            "rerank_time_ms": rerank_time_ms,
        }

    def _session_docs_sufficient(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        intent: Optional[str],
        action: Optional[str],
        query_vehicle_type: str,
        query_km: Optional[float],
    ) -> bool:
        ready, above_threshold = self._meets_evidence_threshold(
            hits=hits,
            min_score=self.settings.session_doc_score_threshold,
            min_evidence=1,
        )
        match_count, topic_mismatch = self._evaluate_trusted_hits(
            question=question,
            hits=hits,
            query_vehicle_type=query_vehicle_type,
            intent=intent,
            action=action,
            query_km=query_km,
        )
        logger.info(
            "session doc quality | above_threshold=%s | match_count=%s | topic_mismatch=%s",
            above_threshold,
            match_count,
            topic_mismatch,
        )
        return ready and match_count > 0 and not topic_mismatch

    def _global_docs_sufficient(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        intent: Optional[str],
        action: Optional[str],
        query_vehicle_type: str,
        query_km: Optional[float],
    ) -> bool:
        ready, above_threshold = self._meets_evidence_threshold(
            hits=hits,
            min_score=self.settings.global_doc_score_threshold,
            min_evidence=1,
        )
        match_count, topic_mismatch = self._evaluate_trusted_hits(
            question=question,
            hits=hits,
            query_vehicle_type=query_vehicle_type,
            intent=intent,
            action=action,
            query_km=query_km,
        )
        logger.info(
            "global doc quality | above_threshold=%s | match_count=%s | topic_mismatch=%s",
            above_threshold,
            match_count,
            topic_mismatch,
        )
        return ready and match_count > 0 and not topic_mismatch

    def _map_legal_hits(self, rows: List[Dict[str, Any]], query_vehicle_type: str) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for row in rows:
            hits.append(
                {
                    "primary_id": row.get("sothutund"),
                    "label": row.get("duong_dan_phan_cap") or row.get("sohieu") or f"CAN_CU_{row.get('sothutund')}",
                    "content": row.get("noidung") or "",
                    "url": row.get("url"),
                    "source_type": "legal_db",
                    "vehicle_type": query_vehicle_type,
                    "hybrid_score": float(row.get("do_tuong_dong") or 0.0),
                    "cross_encoder_score": 0.0,
                    "vehicle_bonus": 0.0,
                    "final_rerank_score": float(row.get("do_tuong_dong") or 0.0),
                    "min_km": row.get("min_km"),
                    "max_km": row.get("max_km"),
                    "km_phu_hop": bool(row.get("km_phu_hop")) if row.get("km_phu_hop") is not None else False,
                    "sohieu": row.get("sohieu"),
                    "sothutund_cha": row.get("sothutund_cha"),
                }
            )
        return hits

    def _meets_evidence_threshold(self, hits: List[Dict[str, Any]], min_score: float, min_evidence: int) -> Tuple[bool, int]:
        above_threshold = [
            item for item in hits if float(item.get("hybrid_score") or item.get("score") or 0.0) >= float(min_score)
        ]
        return len(above_threshold) >= min_evidence, len(above_threshold)

    def _is_exact_legal_query(
        self,
        intent: Optional[str],
        action: Optional[str],
        query_km: Optional[float],
    ) -> bool:
        if intent in EXACT_LEGAL_INTENTS:
            return True
        if action == "qua_toc_do" and query_km is not None:
            return True
        return False

    def _intent_match_count(
        self,
        hits: List[Dict[str, Any]],
        query_vehicle_type: str,
        action: Optional[str],
        query_km: Optional[float],
    ) -> int:
        count = 0
        for item in hits[:3]:
            text = normalize_legal_text(f"{item.get('label') or ''} {item.get('content') or ''}")
            matched = False
            if query_vehicle_type != "khac" and self._vehicle_text_bonus(query_vehicle_type, text) > 0:
                matched = True
            if action and self._action_bonus(action, text) > 0:
                matched = True
            if query_km is not None and item.get("km_phu_hop") is True:
                matched = True
            if matched:
                count += 1
        return count

    def _evaluate_trusted_hits(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        query_vehicle_type: str,
        intent: Optional[str],
        action: Optional[str],
        query_km: Optional[float],
    ) -> Tuple[int, bool]:
        query_text = normalize_legal_text(question)
        query_tokens = {
            token
            for token in re.findall(r"\w+", query_text)
            if len(token) >= 3 and token not in {"theo", "hien", "nay", "cho", "voi", "nguoi"}
        }
        match_count = 0
        for item in hits[:3]:
            text = normalize_legal_text(f"{item.get('label') or ''} {(item.get('content') or '')[:1200]}")
            hit_tokens = set(re.findall(r"\w+", text))
            overlap = len(query_tokens & hit_tokens)
            matched = overlap >= 2
            if query_vehicle_type != "khac" and self._vehicle_text_bonus(query_vehicle_type, text) > 0:
                matched = True
            if action and self._action_bonus(action, text) > 0:
                matched = True
            if query_km is not None and item.get("km_phu_hop") is True:
                matched = True
            if intent == "doi_tuong_ap_dung" and any(token in text for token in ("gplx", "giay phep", "hang", "phan hang")):
                matched = True
            if matched:
                match_count += 1
        return match_count, bool(hits) and match_count == 0

    def _rerank_results(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        query_vehicle_type: str,
        query_km: Optional[float],
        action: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not hits:
            return []

        query_action = action or detect_legal_action(question)
        pairs = []
        for item in hits:
            content = (item.get("content") or "").strip()
            label = (item.get("label") or "").strip()
            pairs.append((question, f"{label}\n{content}" if label else content))

        if self.reranker is not None:
            try:
                ce_scores = self.reranker.predict(pairs)
            except Exception as exc:
                logger.warning("reranker predict failed: %s", exc)
                ce_scores = [0.0 for _ in pairs]
        else:
            ce_scores = [0.0 for _ in pairs]

        reranked: List[Dict[str, Any]] = []
        for item, ce_score in zip(hits, ce_scores):
            label = item.get("label") or ""
            content = item.get("content") or ""
            hybrid_score = float(item.get("hybrid_score") or 0.0)
            text = f"{label}\n{content}"
            vehicle_bonus = self._vehicle_text_bonus(query_vehicle_type, text)
            km_bonus = self._km_bonus(query_km, item.get("min_km"), item.get("max_km"), text)
            action_bonus = self._action_bonus(query_action, text)
            km_match_bonus = 0.0
            if query_km is not None and item.get("km_phu_hop") is True:
                km_match_bonus = 0.45
            elif query_km is not None and query_action == "qua_toc_do":
                km_match_bonus = -0.18

            enriched = dict(item)
            enriched["cross_encoder_score"] = float(ce_score)
            enriched["vehicle_bonus"] = float(vehicle_bonus)
            enriched["km_bonus"] = float(km_bonus)
            enriched["km_match_bonus"] = float(km_match_bonus)
            enriched["action_bonus"] = float(action_bonus)
            enriched["final_rerank_score"] = float(
                hybrid_score * 0.65
                + float(ce_score) * 0.15
                + vehicle_bonus
                + km_bonus
                + action_bonus
                + km_match_bonus
            )
            reranked.append(enriched)

        reranked.sort(key=lambda x: x.get("final_rerank_score") or 0.0, reverse=True)
        return reranked[: self.rerank_final_top_k]

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
