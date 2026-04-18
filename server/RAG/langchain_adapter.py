import logging
import time
import unicodedata
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.conversation_manager import ConversationManager
from services.legal_query_context import build_effective_legal_question
from services.retrieval_service import RetrievalService

logger = logging.getLogger("LANGCHAIN_ADAPTER")

LEGAL_KEYWORDS = (
    "luat",
    "nghi dinh",
    "quy dinh",
    "xu phat",
    "muc phat",
    "vi pham",
    "gplx",
    "giay phep lai xe",
    "nong do con",
    "bien bao",
    "xe may",
    "o to",
    "oto",
    "xe dap",
    "di bo",
    "dang ky xe",
    "giay to",
    "hanh chinh",
    "giao thong",
    "vuot den do",
    "den do",
    "qua toc do",
    "toc do",
    "lan duong",
    "bao nhieu tien",
    "bao nhieu",
    "xe o to",
    "giu xe",
    "tam giu",
    "can cu",
)


class LangChainAdapter:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        answer_service: AnswerService,
        conversation_manager: ConversationManager,
        settings: RAGSettings,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.answer_service = answer_service
        self.conversation_manager = conversation_manager
        self.settings = settings
        self.general_chat_model = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.answer_model_name,
            temperature=0.3,
        )
        self.general_chat_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Ban la tro ly AI huu ich cua Fishy. "
                        "Tra loi ro rang, than thien, va trung thuc. "
                        "Neu cau hoi lien quan den phap ly chuyen sau ma ban khong co ngu can cu, "
                        "hay noi ro gioi han thay vi khang dinh chac chan."
                    ),
                ),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{question}"),
            ]
        )

    def route_question(self, question: str) -> str:
        normalized = self._normalize_text(question)
        if any(keyword in normalized for keyword in LEGAL_KEYWORDS):
            return "legal_rag"
        return "general_chat"

    def route_question_with_history(self, question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        recent_user_messages: List[str] = []
        for item in reversed(history or []):
            if item.get("role") != "user":
                continue
            content = (item.get("content") or "").strip()
            if not content:
                continue
            recent_user_messages.append(content)
            if len(recent_user_messages) >= 2:
                break
        combined = " ".join(list(reversed(recent_user_messages)) + [question]).strip()
        normalized = self._normalize_text(combined)
        if any(keyword in normalized for keyword in LEGAL_KEYWORDS):
            return "legal_rag"
        return "general_chat"

    async def chat(
        self,
        question: str,
        session_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        active_session_id = session_id or str(uuid.uuid4())
        history = self._build_history(active_session_id, chat_history)
        route = self.route_question_with_history(question, history)
        start_time = time.perf_counter()

        logger.info(
            "chat incoming | session_id=%s | route=%s | question=%s",
            active_session_id,
            route,
            question[:200],
        )

        if route == "legal_rag":
            result = self.handle_legal(question=question, session_id=active_session_id, history=history)
        else:
            result = await self.handle_general(question=question, session_id=active_session_id, history=history)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        answer = result.get("answer", "").strip()

        self.conversation_manager.append_user_message(active_session_id, question)
        self.conversation_manager.append_assistant_message(active_session_id, answer)

        evaluation_payload = result.get("evaluation") or {}
        evaluation_payload["timings"] = {
            **(evaluation_payload.get("timings") or {}),
            "latency_ms": latency_ms,
            "retrieval_time_ms": result.get("meta", {}).get("retrieval_time_ms"),
            "rerank_time_ms": result.get("meta", {}).get("rerank_time_ms"),
            "gen_time_ms": result.get("meta", {}).get("gen_time_ms"),
        }
        result["evaluation"] = evaluation_payload
        result["session_id"] = active_session_id
        result["route"] = route
        result["meta"] = {
            **result.get("meta", {}),
            "route_selected": route,
            "answer_mode": route,
            "latency_ms": latency_ms,
            "history_length": len(self.conversation_manager.get_history(active_session_id)),
        }
        logger.info(
            "chat completed | session_id=%s | route=%s | used_firecrawl=%s | source_count=%s | latency_ms=%s",
            active_session_id,
            route,
            result.get("used_firecrawl", False),
            len(result.get("sources", [])),
            latency_ms,
        )
        logger.info("server output | session_id=%s | answer=%s", active_session_id, answer[:500])
        return result

    def handle_legal(self, question: str, session_id: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        logger.info("legal route start | session_id=%s", session_id)
        context = build_effective_legal_question(question, history)
        original_question = str(context["original_question"])
        effective_question = str(context["effective_question"])
        intent = str(context.get("intent") or "followup_khong_ro")
        action = str(context.get("action") or "")
        query_vehicle_type = str(context.get("vehicle_type") or "khac")
        query_km = context.get("query_km")
        is_followup = bool(context.get("is_followup"))
        rewrite_confidence = float(context.get("rewrite_confidence") or 0.0)

        logger.info(
            "legal question context | session_id=%s | original=%s | effective=%s | intent=%s | action=%s | vehicle_type=%s | query_km=%s | is_followup=%s | rewrite_confidence=%s",
            session_id,
            original_question[:200],
            effective_question[:200],
            intent,
            action,
            query_vehicle_type,
            query_km,
            is_followup,
            rewrite_confidence,
        )

        retrieval = self.retrieval_service.retrieve_context(
            question=effective_question,
            original_question=original_question,
            effective_question=effective_question,
            query_vehicle_type=query_vehicle_type,
            query_km=query_km,
            intent=intent,
            action=action,
            rewrite_confidence=rewrite_confidence,
            history=history,
        )
        final_hits = retrieval.get("combined_results", [])
        evidence = self.answer_service.assess_context(
            question=effective_question,
            hits=final_hits,
            min_score=self.settings.rag_legal_score_threshold,
            min_evidence=1 if intent == "giai_thich_chung" else self.settings.rag_min_legal_evidence,
            debug_meta={
                "intent": intent,
                "action": action,
                "vehicle_type": query_vehicle_type,
                "query_km": query_km,
                "is_followup": is_followup,
                "rewrite_confidence": rewrite_confidence,
                "topic_mismatch": retrieval.get("topic_mismatch", False),
            },
        )
        logger.info(
            "evidence gate | session_id=%s | pass=%s | reason=%s | legal_results=%s | km_match_hits=%s",
            session_id,
            not evidence["insufficient_context"],
            evidence["reason"],
            len(retrieval.get("legal_results", [])),
            retrieval.get("km_match_count", 0),
        )

        if not final_hits or evidence["insufficient_context"]:
            fallback_result = self._run_trusted_second_pass(
                session_id=session_id,
                original_question=original_question,
                effective_question=effective_question,
                history=history,
                query_vehicle_type=query_vehicle_type,
                query_km=query_km,
                intent=intent,
                action=action,
                is_followup=is_followup,
                rewrite_confidence=rewrite_confidence,
                reason=evidence["reason"] if evidence["insufficient_context"] else "no_legal_hits",
            )
            if fallback_result is not None:
                return fallback_result
            return self._build_safe_legal_response(
                retrieval=retrieval,
                final_hits=final_hits,
                effective_question=effective_question,
                query_vehicle_type=query_vehicle_type,
                query_km=query_km,
                intent=intent,
                action=action,
                rewrite_confidence=rewrite_confidence,
            )

        gen_start = time.perf_counter()
        answer_bundle = self.answer_service.generate_answer(
            question=original_question,
            hits=final_hits,
            history=history,
            effective_question=effective_question,
            debug_meta={
                "intent": intent,
                "action": action,
                "vehicle_type": query_vehicle_type,
                "query_km": query_km,
                "is_followup": is_followup,
                "rewrite_confidence": rewrite_confidence,
                "topic_mismatch": retrieval.get("topic_mismatch", False),
            },
        )
        gen_time_ms = round((time.perf_counter() - gen_start) * 1000, 2)
        logger.info(
            "legal answer generated | session_id=%s | answer_insufficient=%s | reason=%s | answer=%s",
            session_id,
            answer_bundle.get("insufficient_context"),
            answer_bundle.get("reason"),
            answer_bundle["answer"][:500],
        )

        if answer_bundle.get("insufficient_context"):
            fallback_result = self._run_trusted_second_pass(
                session_id=session_id,
                original_question=original_question,
                effective_question=effective_question,
                history=history,
                query_vehicle_type=query_vehicle_type,
                query_km=query_km,
                intent=intent,
                action=action,
                is_followup=is_followup,
                rewrite_confidence=rewrite_confidence,
                reason=str(answer_bundle.get("reason") or "answer_insufficient"),
            )
            if fallback_result is not None:
                return fallback_result

        return {
            "success": True,
            "answer": answer_bundle["answer"],
            "sources": answer_bundle.get("sources", []),
            "used_fallback": retrieval.get("used_fallback", False),
            "used_firecrawl": retrieval.get("firecrawl_called", False),
            "evaluation": self._build_evaluation_payload(
                final_hits=final_hits,
                candidate_hits=retrieval.get("candidate_results", []),
                timings={
                    "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                    "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                    "gen_time_ms": gen_time_ms,
                },
                detected_vehicle_type=query_vehicle_type,
            ),
            "debug": self._build_debug_info(retrieval, branch="legal_rag", effective_question=effective_question),
            "meta": {
                "used_legal_retrieval": True,
                "source_count": len(answer_bundle.get("sources", [])),
                "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                "gen_time_ms": gen_time_ms,
                "detected_vehicle_type": query_vehicle_type,
                "effective_question": effective_question,
                "query_km": query_km,
                "intent": intent,
                "action": action,
                "rewrite_confidence": rewrite_confidence,
            },
        }

    def _run_trusted_second_pass(
        self,
        session_id: str,
        original_question: str,
        effective_question: str,
        history: List[Dict[str, str]],
        query_vehicle_type: str,
        query_km: Any,
        intent: str,
        action: str,
        is_followup: bool,
        rewrite_confidence: float,
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        logger.info("second pass fallback | session_id=%s | reason=%s", session_id, reason)
        retrieval = self.retrieval_service.retrieve_context(
            question=effective_question,
            original_question=original_question,
            effective_question=effective_question,
            query_vehicle_type=query_vehicle_type,
            query_km=query_km,
            intent=intent,
            action=action,
            rewrite_confidence=rewrite_confidence,
            force_trusted_fallback=True,
            history=history,
        )
        fallback_hits = retrieval.get("trusted_cache_results", [])
        if not fallback_hits:
            return None

        gen_start = time.perf_counter()
        answer_bundle = self.answer_service.generate_answer(
            question=original_question,
            hits=fallback_hits,
            history=history,
            effective_question=effective_question,
            debug_meta={
                "intent": intent,
                "action": action,
                "vehicle_type": query_vehicle_type,
                "query_km": query_km,
                "is_followup": is_followup,
                "rewrite_confidence": rewrite_confidence,
                "topic_mismatch": retrieval.get("topic_mismatch", False),
            },
        )
        gen_time_ms = round((time.perf_counter() - gen_start) * 1000, 2)
        logger.info(
            "second pass answer | session_id=%s | answer_insufficient=%s | reason=%s",
            session_id,
            answer_bundle.get("insufficient_context"),
            answer_bundle.get("reason"),
        )
        if answer_bundle.get("insufficient_context"):
            return None

        return {
            "success": True,
            "answer": answer_bundle["answer"],
            "sources": answer_bundle.get("sources", []),
            "used_fallback": True,
            "used_firecrawl": retrieval.get("firecrawl_called", False),
            "evaluation": self._build_evaluation_payload(
                final_hits=fallback_hits,
                candidate_hits=retrieval.get("candidate_results", []),
                timings={
                    "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                    "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                    "gen_time_ms": gen_time_ms,
                },
                detected_vehicle_type=query_vehicle_type,
            ),
            "debug": self._build_debug_info(retrieval, branch="legal_rag", effective_question=effective_question),
            "meta": {
                "used_legal_retrieval": True,
                "source_count": len(answer_bundle.get("sources", [])),
                "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                "gen_time_ms": gen_time_ms,
                "detected_vehicle_type": query_vehicle_type,
                "effective_question": effective_question,
                "query_km": query_km,
                "intent": intent,
                "action": action,
                "rewrite_confidence": rewrite_confidence,
            },
        }

    def _build_safe_legal_response(
        self,
        retrieval: Dict[str, Any],
        final_hits: List[Dict[str, Any]],
        effective_question: str,
        query_vehicle_type: str,
        query_km: Any,
        intent: str,
        action: str,
        rewrite_confidence: float,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "answer": "Chưa đủ căn cứ trong dữ liệu retrieve được để kết luận chính xác.",
            "sources": [],
            "used_fallback": retrieval.get("used_fallback", False),
            "used_firecrawl": retrieval.get("firecrawl_called", False),
            "evaluation": self._build_evaluation_payload(
                final_hits=final_hits,
                candidate_hits=retrieval.get("candidate_results", []),
                timings={
                    "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                    "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                    "gen_time_ms": 0.0,
                },
                detected_vehicle_type=query_vehicle_type,
            ),
            "debug": self._build_debug_info(retrieval, branch="legal_rag", effective_question=effective_question),
            "meta": {
                "used_legal_retrieval": True,
                "source_count": 0,
                "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                "gen_time_ms": 0.0,
                "detected_vehicle_type": query_vehicle_type,
                "effective_question": effective_question,
                "query_km": query_km,
                "intent": intent,
                "action": action,
                "rewrite_confidence": rewrite_confidence,
            },
        }

    async def handle_general(self, question: str, session_id: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        logger.info("general route start | session_id=%s", session_id)
        lc_history = self._to_langchain_messages(history)
        chain = self.general_chat_prompt | self.general_chat_model
        response = await chain.ainvoke({"question": question, "history": lc_history})
        answer = response.content if hasattr(response, "content") else str(response)
        return {
            "success": True,
            "answer": answer,
            "sources": [],
            "used_fallback": False,
            "used_firecrawl": False,
            "evaluation": {
                "detected_vehicle_type": "khac",
                "candidate_hits": [],
                "hits": [],
                "timings": {
                    "retrieval_time_ms": 0.0,
                    "rerank_time_ms": 0.0,
                    "gen_time_ms": 0.0,
                },
            },
            "debug": {
                "branch": "general_chat",
                "legal_results": 0,
                "trusted_cache_results": 0,
                "firecrawl_called": False,
                "searched_sources_count": 0,
                "scraped_urls_count": 0,
                "firecrawl_cached": 0,
                "candidate_results": 0,
                "final_hits": 0,
                "detected_vehicle_type": "khac",
            },
            "meta": {
                "used_legal_retrieval": False,
                "source_count": 0,
                "retrieval_time_ms": 0.0,
                "rerank_time_ms": 0.0,
                "gen_time_ms": 0.0,
                "detected_vehicle_type": "khac",
            },
        }

    def _build_history(self, session_id: str, chat_history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
        merged: List[Dict[str, str]] = []
        seen: Set[Tuple[str, str]] = set()
        for source in [self.conversation_manager.get_history(session_id), chat_history or []]:
            for item in source:
                role = item.get("role")
                content = (item.get("content") or "").strip()
                if role not in {"user", "assistant"} or not content:
                    continue
                key = (role, content)
                if key in seen:
                    continue
                seen.add(key)
                merged.append({"role": role, "content": content})
        return merged

    def _to_langchain_messages(self, history: List[Dict[str, str]]) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        for item in history:
            content = (item.get("content") or "").strip()
            if not content:
                continue
            if item.get("role") == "user":
                messages.append(HumanMessage(content=content))
            elif item.get("role") == "assistant":
                messages.append(AIMessage(content=content))
        return messages

    def _build_debug_info(
        self,
        retrieval: Dict[str, Any],
        branch: str,
        effective_question: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "branch": branch,
            "rpc_selected": retrieval.get("rpc_selected"),
            "v4_error_reason": retrieval.get("v4_error_reason"),
            "legal_results": len(retrieval.get("legal_results", [])),
            "trusted_cache_results": len(retrieval.get("trusted_cache_results", [])),
            "candidate_results": len(retrieval.get("candidate_results", [])),
            "final_hits": len(retrieval.get("combined_results", [])),
            "firecrawl_called": retrieval.get("firecrawl_called", False),
            "searched_sources_count": retrieval.get("searched_sources_count", 0),
            "scraped_urls_count": retrieval.get("scraped_urls_count", 0),
            "firecrawl_cached": retrieval.get("firecrawl_cached", 0),
            "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
            "query_km": retrieval.get("query_km"),
            "intent": retrieval.get("intent"),
            "action": retrieval.get("action"),
            "rewrite_confidence": retrieval.get("rewrite_confidence"),
            "km_match_count": retrieval.get("km_match_count", 0),
            "intent_match_count": retrieval.get("intent_match_count", 0),
            "topic_mismatch": retrieval.get("topic_mismatch", False),
            "final_fallback_reason": retrieval.get("final_fallback_reason"),
            "effective_question": effective_question or retrieval.get("effective_question"),
        }

    def _build_evaluation_payload(
        self,
        final_hits: List[Dict[str, Any]],
        candidate_hits: Optional[List[Dict[str, Any]]] = None,
        timings: Optional[Dict[str, Any]] = None,
        detected_vehicle_type: str = "khac",
    ) -> Dict[str, Any]:
        def normalize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return [
                {
                    "primary_id": item.get("primary_id"),
                    "label": item.get("label"),
                    "content": item.get("content"),
                    "url": item.get("url"),
                    "source_type": item.get("source_type"),
                    "vehicle_type": item.get("vehicle_type"),
                    "hybrid_score": item.get("hybrid_score"),
                    "cross_encoder_score": item.get("cross_encoder_score"),
                    "vehicle_bonus": item.get("vehicle_bonus"),
                    "km_bonus": item.get("km_bonus"),
                    "action_bonus": item.get("action_bonus"),
                    "final_rerank_score": item.get("final_rerank_score"),
                    "rerank_score": item.get("final_rerank_score", item.get("cross_encoder_score")),
                    "min_km": item.get("min_km"),
                    "max_km": item.get("max_km"),
                    "km_phu_hop": item.get("km_phu_hop"),
                }
                for item in items
            ]

        return {
            "detected_vehicle_type": detected_vehicle_type,
            "candidate_hits": normalize(candidate_hits or []),
            "hits": normalize(final_hits),
            "timings": timings or {},
        }

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return normalized.replace("đ", "d").replace("Đ", "D")
