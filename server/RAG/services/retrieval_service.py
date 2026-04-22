import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from sentence_transformers import CrossEncoder, SentenceTransformer
from supabase import Client

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.global_doc_service import GlobalDocService
from services.legal_query_context import (
    build_effective_legal_question,
    detect_legal_action,
    detect_vehicle_type,
    extract_km,
    normalize_legal_text,
)
from services.source_formatter import format_db_source, format_user_facing_source
logger = logging.getLogger("RETRIEVAL_SERVICE")
EXACT_LEGAL_INTENTS = {"muc_phat", "can_cu_phap_ly", "tuoc_gplx", "tam_giu_phuong_tien"}


class RetrievalService:
    def __init__(
        self,
        supabase: Client,
        embedding_model: SentenceTransformer,
        settings: RAGSettings,
        global_doc_service: GlobalDocService,
        answer_service: AnswerService,
    ) -> None:
        self.supabase = supabase
        self.embedding_model = embedding_model
        self.settings = settings
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
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        _ = session_id

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
            response = self.supabase.rpc(self.settings.legal_retrieval_rpc_name, rpc_payload).execute()
            hits = self._map_legal_hits(response.data or [], query_vehicle_type=query_vehicle_type)
            logger.info(
                "legal retrieval rpc | rpc_selected=%s | results=%s | vehicle_type=%s | query_km=%s",
                self.settings.legal_retrieval_rpc_name,
                len(hits),
                query_vehicle_type,
                query_km,
            )
            return {
                "hits": hits,
                "legal_db_unavailable": False,
                "rpc_selected": self.settings.legal_retrieval_rpc_name,
                "v4_error_reason": None,
            }
        except Exception as exc:
            logger.warning(
                "legal retrieval rpc failed | rpc_selected=%s | reason=%s",
                self.settings.legal_retrieval_rpc_name,
                exc,
            )
            try:
                response = self.supabase.rpc(self.settings.legacy_legal_retrieval_rpc_name, rpc_payload).execute()
                hits = self._map_legal_hits(response.data or [], query_vehicle_type=query_vehicle_type)
                logger.info(
                    "legal retrieval fallback rpc | rpc_selected=%s | results=%s",
                    self.settings.legacy_legal_retrieval_rpc_name,
                    len(hits),
                )
                return {
                    "hits": hits,
                    "legal_db_unavailable": False,
                    "rpc_selected": self.settings.legacy_legal_retrieval_rpc_name,
                    "v4_error_reason": str(exc),
                }
            except Exception as legacy_exc:
                logger.warning(
                    "legal retrieval legacy fallback failed | rpc_selected=%s | reason=%s",
                    self.settings.legacy_legal_retrieval_rpc_name,
                    legacy_exc,
                )
                return {
                    "hits": [],
                    "legal_db_unavailable": True,
                    "rpc_selected": self.settings.legal_retrieval_rpc_name,
                    "v4_error_reason": str(legacy_exc),
                }

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

        normalized_question = normalize_legal_text(original_question or effective_question)
        canonical_legal_query = effective_question
        query_vector = self.embedding_model.encode("query: " + canonical_legal_query, normalize_embeddings=True).tolist()
        original_query_vector = None
        normalized_query_vector = None
        if original_question and original_question != canonical_legal_query:
            original_query_vector = self.embedding_model.encode(
                "query: " + original_question, normalize_embeddings=True
            ).tolist()
        if normalized_question and normalized_question not in {canonical_legal_query, original_question}:
            normalized_query_vector = self.embedding_model.encode(
                "query: " + normalized_question, normalize_embeddings=True
            ).tolist()
        logger.info(
            "retrieval query variants | normalized_question=%s | canonical_legal_query=%s",
            normalized_question[:200],
            canonical_legal_query[:200],
        )

        legal_results: List[Dict[str, Any]] = []
        candidate_hits: List[Dict[str, Any]] = []
        final_hits: List[Dict[str, Any]] = []
        legal_db_unavailable = False
        v4_error_reason = None
        km_match_count = 0
        intent_match_count = 0
        topic_mismatch = False
        used_fallback = False
        fallback_reason = ""

        legal_search = self.search_legal_db(
            question=effective_question,
            query_vector=query_vector,
            query_km=query_km,
            query_vehicle_type=query_vehicle_type,
            session_id=session_id,
        )
        legal_results = legal_search["hits"]
        legal_db_unavailable = bool(legal_search["legal_db_unavailable"])
        v4_error_reason = legal_search["v4_error_reason"]
        candidate_hits = list(legal_results)

        _, legal_above_threshold = self._meets_evidence_threshold(
            hits=legal_results,
            min_score=self.settings.rag_legal_score_threshold,
            min_evidence=self.settings.rag_min_legal_evidence,
        )
        km_match_count = sum(1 for item in legal_results if item.get("km_phu_hop") is True)
        generic_legal_query = (
            query_vehicle_type == "khac"
            and not action
            and query_km is None
            and not exact_legal_query
        )

        if generic_legal_query:
            intent_match_count, topic_mismatch = self._evaluate_trusted_hits(
                question=effective_question,
                hits=legal_results,
                query_vehicle_type=query_vehicle_type,
                intent=intent,
                action=action,
                query_km=query_km,
            )
        else:
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

        if legal_db_unavailable:
            used_fallback = True
            fallback_reason = "legal_db_unavailable"
        elif len(final_hits) < self.settings.rag_min_legal_evidence:
            used_fallback = True
            fallback_reason = "too_few_legal_hits"
        elif topic_mismatch:
            used_fallback = True
            fallback_reason = "topic_mismatch"
        elif query_km is not None and action == "qua_toc_do" and km_match_count == 0:
            used_fallback = True
            fallback_reason = "missing_km_match"

        used_global_docs = any(item.get("source_type") == "admin_upload" for item in final_hits)
        global_doc_hits = [item for item in legal_results if item.get("source_type") == "admin_upload"]
        global_doc_top_score = float(
            global_doc_hits[0].get("final_rerank_score") or global_doc_hits[0].get("hybrid_score") or 0.0
        ) if global_doc_hits else 0.0
        fallback_to_legal_db = False

        retrieval_time_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "retrieval fallback summary | global_doc_hits=%s | legal_results=%s | used_global_docs=%s | fallback_to_legal_db=%s | used_fallback=%s | final_fallback_reason=%s",
            len(global_doc_hits),
            len(legal_results),
            used_global_docs,
            fallback_to_legal_db,
            used_fallback,
            fallback_reason or "none",
        )

        return {
            "global_doc_results": global_doc_hits,
            "global_doc_hits": len(global_doc_hits),
            "global_doc_top_score": global_doc_top_score,
            "used_global_docs": used_global_docs,

            "fallback_to_legal_db": fallback_to_legal_db,
            "legal_results": legal_results,
            "candidate_results": candidate_hits,
            "combined_results": final_hits,
            "used_fallback": used_fallback,
            "legal_db_unavailable": legal_db_unavailable,
            "rpc_selected": legal_search["rpc_selected"],
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
            "final_fallback_reason": fallback_reason,
            "original_question": original_question,
            "normalized_question": normalized_question,
            "canonical_legal_query": canonical_legal_query,
            "effective_question": effective_question,
            "retrieval_time_ms": retrieval_time_ms,
            "rerank_time_ms": rerank_time_ms,
        }

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
        top_hit = hits[0] if hits else {}
        top_score = float(top_hit.get("final_rerank_score") or top_hit.get("hybrid_score") or 0.0)
        exact_score = float(top_hit.get("exact_score") or 0.0)
        text_score = float(top_hit.get("text_score") or top_hit.get("lexical_score") or 0.0)
        dense_score = float(top_hit.get("semantic_score") or 0.0)
        metadata_match_score = float(top_hit.get("metadata_match_score") or 0.0)
        linh_vuc = normalize_legal_text(str(top_hit.get("linh_vuc") or ""))
        query_is_general = not self._is_exact_legal_query(intent=intent, action=action, query_km=query_km)
        test_domain_match = linh_vuc == "test"
        heuristic_pass = False
        if exact_score >= 0.55 or text_score >= 0.55 or metadata_match_score >= 0.7:
            heuristic_pass = True
        elif test_domain_match and (top_score >= 0.28 or text_score >= 0.25 or exact_score >= 0.25 or dense_score >= 0.28):
            heuristic_pass = True
        elif query_is_general and (
            top_score >= 0.34 and (match_count > 0 or text_score >= 0.35 or exact_score >= 0.35 or dense_score >= 0.4)
        ):
            heuristic_pass = True
        logger.info(
            "global doc quality | above_threshold=%s | match_count=%s | topic_mismatch=%s | exact_score=%s | text_score=%s | dense_score=%s | metadata_match_score=%s | linh_vuc=%s",
            above_threshold,
            match_count,
            topic_mismatch,
            round(exact_score, 4),
            round(text_score, 4),
            round(dense_score, 4),
            round(metadata_match_score, 4),
            linh_vuc or "none",
        )
        if topic_mismatch and not test_domain_match:
            return False
        return (ready and match_count > 0 and not topic_mismatch) or heuristic_pass

    def _map_legal_hits(self, rows: List[Dict[str, Any]], query_vehicle_type: str) -> List[Dict[str, Any]]:
        ancestor_map = self._load_legal_ancestors(rows)
        hits: List[Dict[str, Any]] = []
        for row in rows:
            primary_id = row.get("sothutund")
            source_table = str(row.get("source_table") or "noidung").strip().lower()
            row_key = f"{source_table}:{primary_id}"
            ancestors = ancestor_map.get(row_key, [])
            source_type = str(row.get("source_type") or ("legal_db" if source_table == "noidung" else "admin_upload")).strip()
            label = (
                format_db_source(row, ancestors=ancestors)
                if source_table == "noidung"
                else format_user_facing_source(
                    {
                        **row,
                        "source_type": source_type,
                        "ancestor_nodes": ancestors,
                    }
                )
            )
            hits.append(
                {
                    "primary_id": primary_id,
                    "label": label,
                    "content": row.get("noidung") or "",
                    "url": row.get("url"),
                    "source_type": source_type,
                    "source_table": source_table,
                    "vehicle_type": query_vehicle_type,
                    "hybrid_score": float(row.get("do_tuong_dong") or 0.0),
                    "cross_encoder_score": 0.0,
                    "vehicle_bonus": 0.0,
                    "final_rerank_score": float(row.get("do_tuong_dong") or 0.0),
                    "min_km": row.get("min_km"),
                    "max_km": row.get("max_km"),
                    "km_phu_hop": bool(row.get("km_phu_hop")) if row.get("km_phu_hop") is not None else False,
                    "sohieu": row.get("sohieu"),
                    "so_hieu": row.get("so_hieu") or row.get("sohieu"),
                    "ten_van_ban": row.get("ten_van_ban") or row.get("title"),
                    "filename": row.get("source_file_name") or row.get("filename"),
                    "section_path": row.get("section_path") or row.get("duong_dan_phan_cap"),
                    "page_start": row.get("page_start"),
                    "page_end": row.get("page_end"),
                    "dieu": self._extract_legal_unit_from_nodes(row, ancestors, "DIEU"),
                    "khoan": self._extract_legal_unit_from_nodes(row, ancestors, "KHOAN"),
                    "diem": self._extract_legal_unit_from_nodes(row, ancestors, "DIEM"),
                    "chapter": self._extract_legal_unit_from_nodes(row, ancestors, "CHUONG"),
                    "ancestor_nodes": ancestors,
                    "sothutund_cha": row.get("sothutund_cha"),
                }
            )
        return hits

    def _load_legal_ancestors(self, rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        row_by_id = {
            f"{str(row.get('source_table') or 'noidung').lower()}:{row.get('sothutund')}": dict(row)
            for row in rows
            if row.get("sothutund") is not None
        }
        unresolved_by_table: Dict[str, set[str]] = {"noidung": set(), "noidung2": set()}
        for row in rows:
            parent_id = row.get("sothutund_cha")
            if parent_id in {None, "", 0}:
                continue
            source_table = str(row.get("source_table") or "noidung").strip().lower()
            unresolved_by_table.setdefault(source_table, set()).add(str(parent_id))

        fetched: Dict[str, Dict[str, Any]] = {}
        select_map = {
            "noidung": "sothutund,sothutund_cha,loai_muc,ky_hieu,sohieu",
            "noidung2": "sothutund,sothutund_cha,loai_muc,ky_hieu,sohieu,section_path,ten_van_ban,source_file_name",
        }
        for table_name, unresolved in unresolved_by_table.items():
            try:
                while unresolved:
                    batch = list(unresolved)[:100]
                    response = self.supabase.table(table_name).select(select_map[table_name]).in_("sothutund", batch).execute()
                    found_rows = response.data or []
                    if not found_rows:
                        break
                    for node in found_rows:
                        node_id = str(node.get("sothutund"))
                        if node_id:
                            fetched[f"{table_name}:{node_id}"] = {**node, "source_table": table_name}
                    unresolved = {
                        str(node.get("sothutund_cha"))
                        for node in found_rows
                        if node.get("sothutund_cha") not in {None, "", 0}
                        and f"{table_name}:{node.get('sothutund_cha')}" not in fetched
                    } | {item for item in unresolved if f"{table_name}:{item}" not in fetched and item not in batch}
            except Exception as exc:
                logger.warning("load legal ancestors failed | table=%s | reason=%s", table_name, exc)

        full_map = {**fetched, **row_by_id}
        ancestor_map: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            lineage: List[Dict[str, Any]] = []
            cursor = row.get("sothutund_cha")
            source_table = str(row.get("source_table") or "noidung").strip().lower()
            visited = set()
            while cursor not in {None, "", 0}:
                cursor_key = str(cursor)
                if cursor_key in visited:
                    break
                visited.add(cursor_key)
                node = full_map.get(f"{source_table}:{cursor_key}")
                if not node:
                    break
                lineage.append(node)
                cursor = node.get("sothutund_cha")
            ancestor_map[f"{source_table}:{row.get('sothutund')}"] = lineage
        return ancestor_map

    def _extract_legal_unit_from_nodes(
        self,
        row: Dict[str, Any],
        ancestors: List[Dict[str, Any]],
        target_type: str,
    ) -> Optional[str]:
        pattern_map = {
            "DIEM": re.compile(r"(?:diem\s+)?([a-zd])(?:\)|\b)", re.I),
            "KHOAN": re.compile(r"khoan\s+(\d+[a-z]?)|\b(\d+[a-z]?)\b", re.I),
            "DIEU": re.compile(r"dieu\s+(\d+[a-z]?)|\b(\d+[a-z]?)\b", re.I),
            "CHUONG": re.compile(r"chuong\s+([ivxlcdm0-9]+)|\b([ivxlcdm0-9]+)\b", re.I),
        }
        for node in [row] + list(ancestors):
            node_type = str(node.get("loai_muc") or "").strip().upper()
            if node_type != target_type:
                continue
            ky_hieu = str(node.get("ky_hieu") or "").strip()
            if not ky_hieu:
                continue
            match = pattern_map[target_type].search(ky_hieu)
            if not match:
                continue
            for group in match.groups():
                if group:
                    return group.lower() if target_type == "DIEM" else group
        return None

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
        for item in hits[:10]:
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
        if query_action == "dua_xe" and re.search(r"\b(dua xe|co vu dua xe|to chuc dua xe)\b", normalized):
            return 0.12
        if query_action == "vuot_den_do" and re.search(r"\b(den do|tin hieu)\b", normalized):
            return 0.12
        if query_action == "qua_toc_do" and re.search(r"\b(toc do|km/h|km)\b", normalized):
            return 0.12
        if query_action == "nong_do_con" and re.search(r"\b(nong do con|co con|bia ruou)\b", normalized):
            return 0.12
        if query_action == "khong_doi_mu" and re.search(r"\b(mu bao hiem|doi mu)\b", normalized):
            return 0.12
        if query_action in {"cho_qua_nguoi", "cho_qua_so_nguoi"} and re.search(
            r"\b(cho qua|so nguoi|tong 3|cho 3)\b", normalized
        ):
            return 0.12
        if query_action == "di_sai_lan" and re.search(r"\b(lan duong|phan duong)\b", normalized):
            return 0.12
        return 0.0
