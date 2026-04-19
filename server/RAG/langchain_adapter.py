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

FOLLOWUP_MARKERS = (
    "con",
    "vay con",
    "the con",
    "truong hop do",
    "neu vay",
    "thi sao",
    "con xe may",
    "con o to",
    "con oto",
)

GENERAL_GUARD_KEYWORDS = LEGAL_KEYWORDS + (
    "dua xe",
    "tuoc bang",
    "tuoc gplx",
    "hanh vi vi pham",
    "bang lai",
    "bang lai xe",
    "boi thuong",
)

STRONG_TRAFFIC_LEGAL_TERMS = (
    "tuan tra kiem soat",
    "giay phep lai xe",
    "xe may chuyen dung",
    "phuong tien giao thong duong bo",
    "nguoi tham gia giao thong",
    "tru diem giay phep",
    "nong do con",
    "vuot den do",
    "dua xe",
    "qua toc do",
    "mu bao hiem",
    "dieu ",
    "khoan ",
    "diem ",
    "chuong ",
    "nghi dinh",
    "luat",
)

LEGAL_DEFINITION_PATTERNS = (
    "la gi",
    "gom gi",
    "bao gom gi",
    "gom nhung gi",
    "gom hoat dong nao",
    "quy dinh gi",
    "bao gom",
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
        self.classifier_model = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.classifier_model_name,
            temperature=0.0,
            timeout=settings.classifier_timeout_seconds,
        )
        self.general_chat_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Ban la tro ly AI huu ich cua Fishy. "
                        "Tra loi ro rang, than thien, va trung thuc. "
                        "Neu cau hoi lien quan den phap ly chuyen sau ma ban khong co ngu can cu, "
                        "hay noi ro gioi han thay vi khang dinh chac chan. "
                        "Khong duoc tu tra loi chi tiet muc phat, can cu phap ly, hay ket luan phap luat giao thong bang tri nho chung khi khong co retrieve can cu cu the."
                    ),
                ),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{question}"),
            ]
        )
        self.legal_classifier_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "Ban la bo phan phan loai intent cho API /chat cua Fishy. "
                        "Chi duoc tra ve dung mot tu duy nhat: YES hoac NO. "
                        "Tra ve YES neu cau hoi lien quan phap luat giao thong duong bo, muc phat, hanh vi vi pham, "
                        "giay phep lai xe, phuong tien, bien bao, dinh nghia phap ly, hoac la follow-up van dang bam vao ngu canh giao thong/phap ly truoc do. "
                        "Neu cau hien tai ngan, mang tinh noi tiep nhu con, vay con, the con, truong hop do, neu vay, thi sao, con xe may, con o to, "
                        "va 2-4 turn gan day dang o ngu canh phap luat giao thong, bat buoc tra ve YES. "
                        "Tra ve NO neu la chao hoi, xa giao, test, cau hoi chung, vi du hello, hi, ok, ban la ai, cam on. "
                        "Khong giai thich. Khong them ky tu nao khac ngoai YES hoac NO."
                    ),
                ),
                ("human", "Chat history gan day:\n{history_text}\n\nCau hoi hien tai:\n{question}"),
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
        normalized_question = self._normalize_text(question)
        strong_definition_signal = self._has_strong_legal_definition_signal(normalized_question)
        strong_traffic_legal_term = self._has_strong_traffic_legal_term(normalized_question)
        force_legal = strong_definition_signal or strong_traffic_legal_term
        force_legal_reason = "definition_signal" if strong_definition_signal else (
            "strong_traffic_legal_term" if strong_traffic_legal_term else "none"
        )

        classifier = {"decision": "NO", "raw_output": "", "fallback_used": False}
        if not force_legal:
            classifier = await self.classify_legal_intent_yes_no(question=question, chat_history=history)
        followup_markers = self._detect_followup_markers(question)
        recent_legal_context = self._has_recent_legal_context(history)
        followup_legal_override = self._should_force_legal_followup(
            question=question,
            chat_history=history,
            recent_legal_context=recent_legal_context,
            followup_markers=followup_markers,
        )
        classifier_decision = "YES" if (force_legal or followup_legal_override) else classifier["decision"]
        general_guard = self._build_general_guard(
            question=question,
            chat_history=history,
            recent_legal_context=recent_legal_context,
            followup_markers=followup_markers,
        )
        rerouted_from_general_to_legal = classifier_decision != "YES" and general_guard["reroute_to_legal"]
        route = "legal_rag" if classifier_decision == "YES" or general_guard["reroute_to_legal"] else "general_chat"
        retrieval_skipped = route != "legal_rag"
        has_global_docs = self.retrieval_service.has_global_docs() if route == "legal_rag" else False
        logger.info(
            "route precheck | session_id=%s | initial_route=%s | has_global_docs=%s | strong_definition_signal=%s | strong_traffic_legal_term=%s | force_legal_before_classifier=%s | force_legal_reason=%s | classifier_decision=%s | classifier_raw_output=%s | classifier_fallback_used=%s | followup_legal_override=%s | followup_markers_detected=%s | recent_legal_context=%s | general_guard_triggered=%s | rerouted_from_general_to_legal=%s | retrieval_skipped=%s",
            active_session_id,
            route,
            has_global_docs,
            strong_definition_signal,
            strong_traffic_legal_term,
            force_legal,
            force_legal_reason,
            classifier_decision,
            classifier["raw_output"][:80],
            classifier["fallback_used"],
            followup_legal_override,
            followup_markers,
            recent_legal_context,
            general_guard["triggered"],
            rerouted_from_general_to_legal,
            retrieval_skipped,
        )
        if retrieval_skipped:
            logger.info(
                "legal retrieval skipped | session_id=%s | skip_legal_retrieval_reason=classifier_no",
                active_session_id,
            )
        elif rerouted_from_general_to_legal:
            logger.info(
                "general guard reroute | session_id=%s | reason=%s",
                active_session_id,
                general_guard["reason"],
            )
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
            "classifier_decision": classifier_decision,
            "classifier_raw_output": classifier["raw_output"],
            "classifier_fallback_used": classifier["fallback_used"],
            "strong_definition_signal": strong_definition_signal,
            "strong_traffic_legal_term": strong_traffic_legal_term,
            "force_legal_before_classifier": force_legal,
            "force_legal_reason": force_legal_reason,
            "followup_legal_override": followup_legal_override,
            "followup_markers_detected": followup_markers,
            "recent_legal_context": recent_legal_context,
            "general_guard_triggered": general_guard["triggered"],
            "rerouted_from_general_to_legal": rerouted_from_general_to_legal,
            "retrieval_skipped": retrieval_skipped,
            "latency_ms": latency_ms,
            "history_length": len(self.conversation_manager.get_history(active_session_id)),
        }
        logger.info(
            "chat completed | session_id=%s | route=%s | source_count=%s | latency_ms=%s",
            active_session_id,
            route,
            len(result.get("sources", [])),
            latency_ms,
        )
        logger.info("server output | session_id=%s | answer=%s", active_session_id, answer[:500])
        return result

    async def classify_legal_intent_yes_no(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        history_text = self._format_classifier_history(chat_history or [])
        raw_output = ""
        fallback_used = False
        try:
            chain = self.legal_classifier_prompt | self.classifier_model
            response = await chain.ainvoke({"question": question, "history_text": history_text})
            raw_output = (response.content if hasattr(response, "content") else str(response) or "").strip()
        except Exception as exc:
            logger.warning("legal intent classifier failed | reason=%s", exc)
            fallback_used = True

        decision = self._parse_classifier_output(raw_output)
        if decision is None:
            fallback_used = True
            decision = self._heuristic_legal_classifier(question=question, chat_history=chat_history)
        return {
            "decision": decision,
            "raw_output": raw_output,
            "fallback_used": fallback_used,
        }

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
            session_id=session_id,
            history=history,
        )
        final_hits = retrieval.get("combined_results", [])
        min_score = (
            self.settings.global_doc_score_threshold
            if retrieval.get("used_global_docs")
            else (
                self.settings.session_doc_score_threshold
                if retrieval.get("used_session_docs")
                else self.settings.rag_legal_score_threshold
            )
        )
        min_evidence = (
            1
            if retrieval.get("used_global_docs") or retrieval.get("used_session_docs") or intent == "giai_thich_chung"
            else self.settings.rag_min_legal_evidence
        )
        evidence = self.answer_service.assess_context(
            question=effective_question,
            hits=final_hits,
            min_score=min_score,
            min_evidence=min_evidence,
            debug_meta={
                "intent": intent,
                "action": action,
                "vehicle_type": query_vehicle_type,
                "query_km": query_km,
                "is_followup": is_followup,
                "rewrite_confidence": rewrite_confidence,
                "topic_mismatch": retrieval.get("topic_mismatch", False),
                "used_session_docs": retrieval.get("used_session_docs", False),
                "min_score_override": min_score,
                "min_evidence_override": min_evidence,
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

        if (retrieval.get("used_global_docs") or retrieval.get("used_session_docs")) and (
            not final_hits or evidence["insufficient_context"]
        ):
            retrieval = self.retrieval_service.retrieve_context(
                question=effective_question,
                original_question=original_question,
                effective_question=effective_question,
                query_vehicle_type=query_vehicle_type,
                query_km=query_km,
                intent=intent,
                action=action,
                rewrite_confidence=rewrite_confidence,
                session_id=session_id,
                history=history,
                skip_session_docs=True,
                skip_global_docs=True,
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

        if not final_hits or evidence["insufficient_context"]:
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
                "used_session_docs": retrieval.get("used_session_docs", False),
                "min_score_override": min_score,
                "min_evidence_override": min_evidence,
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
            if retrieval.get("used_global_docs") or retrieval.get("used_session_docs"):
                retrieval = self.retrieval_service.retrieve_context(
                    question=effective_question,
                    original_question=original_question,
                    effective_question=effective_question,
                    query_vehicle_type=query_vehicle_type,
                    query_km=query_km,
                    intent=intent,
                    action=action,
                    rewrite_confidence=rewrite_confidence,
                    session_id=session_id,
                    history=history,
                    skip_session_docs=True,
                    skip_global_docs=True,
                )
                final_hits = retrieval.get("combined_results", [])
                if final_hits:
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
                    if not answer_bundle.get("insufficient_context"):
                        return {
                            "success": True,
                            "answer": answer_bundle["answer"],
                            "sources": answer_bundle.get("sources", []),
                            "used_fallback": retrieval.get("used_fallback", False),
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
                            "debug": self._build_debug_info(
                                retrieval,
                                branch="legal_rag",
                                effective_question=effective_question,
                            ),
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

        return {
            "success": True,
            "answer": answer_bundle["answer"],
            "sources": answer_bundle.get("sources", []),
            "used_fallback": retrieval.get("used_fallback", False),
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
            "answer": "Chua du can cu trong du lieu retrieve duoc de ket luan chinh xac.",
            "sources": [],
            "used_fallback": retrieval.get("used_fallback", False),
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
        general_guard = self._build_general_guard(
            question=question,
            chat_history=history,
            recent_legal_context=self._has_recent_legal_context(history),
            followup_markers=self._detect_followup_markers(question),
        )
        if general_guard["triggered"]:
            logger.info(
                "general guard activated | session_id=%s | reroute=%s | reason=%s",
                session_id,
                general_guard["reroute_to_legal"],
                general_guard["reason"],
            )
        if general_guard["reroute_to_legal"]:
            return self.handle_legal(question=question, session_id=session_id, history=history)
        if general_guard["triggered"]:
            return self._build_safe_general_legal_response(reason=general_guard["reason"])

        lc_history = self._to_langchain_messages(history)
        chain = self.general_chat_prompt | self.general_chat_model
        response = await chain.ainvoke({"question": question, "history": lc_history})
        answer = response.content if hasattr(response, "content") else str(response)
        return {
            "success": True,
            "answer": answer,
            "sources": [],
            "used_fallback": False,
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

    def _build_safe_general_legal_response(self, reason: str) -> Dict[str, Any]:
        return {
            "success": True,
            "answer": (
                "Cau nay lien quan den quy dinh phap luat giao thong. "
                "Toi can tra cuu can cu cu the de tra loi chinh xac, thay vi dua vao tri nho chung."
            ),
            "sources": [],
            "used_fallback": False,
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
                "branch": "general_chat_guarded",
                "legal_results": 0,
                "candidate_results": 0,
                "final_hits": 0,
                "detected_vehicle_type": "khac",
                "general_guard_reason": reason,
            },
            "meta": {
                "used_legal_retrieval": False,
                "source_count": 0,
                "retrieval_time_ms": 0.0,
                "rerank_time_ms": 0.0,
                "gen_time_ms": 0.0,
                "detected_vehicle_type": "khac",
                "general_guard_triggered": True,
                "general_guard_reason": reason,
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

    def _format_classifier_history(self, history: List[Dict[str, str]]) -> str:
        snippets: List[str] = []
        for item in history[-6:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            snippets.append(f"{role}: {content[:200]}")
        return "\n".join(snippets) if snippets else "(khong co)"

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
            "used_global_docs": retrieval.get("used_global_docs", False),
            "global_doc_hits": retrieval.get("global_doc_hits", 0),
            "global_doc_top_score": retrieval.get("global_doc_top_score", 0.0),
            "used_session_docs": retrieval.get("used_session_docs", False),
            "session_doc_hits": retrieval.get("session_doc_hits", 0),
            "session_doc_source_count": retrieval.get("session_doc_source_count", 0),
            "candidate_results": len(retrieval.get("candidate_results", [])),
            "final_hits": len(retrieval.get("combined_results", [])),
            "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
            "query_km": retrieval.get("query_km"),
            "intent": retrieval.get("intent"),
            "action": retrieval.get("action"),
            "rewrite_confidence": retrieval.get("rewrite_confidence"),
            "km_match_count": retrieval.get("km_match_count", 0),
            "intent_match_count": retrieval.get("intent_match_count", 0),
            "normalized_question": retrieval.get("normalized_question"),
            "canonical_legal_query": retrieval.get("canonical_legal_query"),
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

    def _parse_classifier_output(self, raw_output: str) -> Optional[str]:
        cleaned = (raw_output or "").strip().upper()
        if cleaned in {"YES", "NO"}:
            return cleaned
        return None

    def _has_strong_traffic_legal_term(self, normalized_question: str) -> bool:
        q = normalized_question or ""
        return any(term in q for term in STRONG_TRAFFIC_LEGAL_TERMS)

    def _has_strong_legal_definition_signal(self, normalized_question: str) -> bool:
        q = normalized_question or ""
        has_legal_term = self._has_strong_traffic_legal_term(q)
        has_definition_pattern = any(pattern in q for pattern in LEGAL_DEFINITION_PATTERNS)
        return has_legal_term and has_definition_pattern

    def _detect_followup_markers(self, question: str) -> List[str]:
        normalized_question = self._normalize_text(question)
        return [marker for marker in FOLLOWUP_MARKERS if marker in normalized_question]

    def _has_recent_legal_context(self, chat_history: Optional[List[Dict[str, str]]]) -> bool:
        recent_messages = [
            (item.get("content") or "").strip()
            for item in (chat_history or [])[-6:]
            if item.get("role") in {"user", "assistant"} and (item.get("content") or "").strip()
        ]
        if not recent_messages:
            return False
        legalish_count = 0
        for content in recent_messages:
            normalized = self._normalize_text(content)
            if any(keyword in normalized for keyword in GENERAL_GUARD_KEYWORDS):
                legalish_count += 1
        return legalish_count >= 2

    def _is_short_followup(self, question: str) -> bool:
        normalized_question = self._normalize_text(question)
        token_count = len([token for token in normalized_question.split() if token])
        return token_count <= 8

    def _should_force_legal_followup(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]],
        recent_legal_context: bool,
        followup_markers: List[str],
    ) -> bool:
        if not recent_legal_context or not followup_markers or not self._is_short_followup(question):
            return False
        normalized_question = self._normalize_text(question)
        recent_text = " ".join(
            (item.get("content") or "").strip()
            for item in (chat_history or [])[-4:]
            if item.get("role") in {"user", "assistant"}
        )
        normalized_recent = self._normalize_text(recent_text)
        if any(keyword in normalized_recent for keyword in GENERAL_GUARD_KEYWORDS):
            return True
        return any(keyword in normalized_question for keyword in ("xe may", "o to", "oto", "dua xe", "phat"))

    def _build_general_guard(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]],
        recent_legal_context: bool,
        followup_markers: List[str],
    ) -> Dict[str, Any]:
        normalized_question = self._normalize_text(question)
        strong_legal_signal = any(keyword in normalized_question for keyword in GENERAL_GUARD_KEYWORDS)
        short_followup = self._is_short_followup(question)
        reroute_to_legal = False
        reason = ""

        if recent_legal_context and followup_markers and short_followup:
            reroute_to_legal = True
            reason = "recent_legal_followup"
        elif recent_legal_context and strong_legal_signal:
            reroute_to_legal = True
            reason = "recent_legal_context_with_legal_signal"

        triggered = reroute_to_legal or strong_legal_signal
        if not reason and strong_legal_signal:
            reason = "strong_legal_signal_in_general"

        return {
            "triggered": triggered,
            "reroute_to_legal": reroute_to_legal,
            "reason": reason or "none",
            "strong_legal_signal": strong_legal_signal,
        }

    def _heuristic_legal_classifier(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        normalized_question = self._normalize_text(question)
        if any(keyword in normalized_question for keyword in LEGAL_KEYWORDS):
            return "YES"

        followup_markers = self._detect_followup_markers(question)
        recent_legal_context = self._has_recent_legal_context(chat_history)
        if self._should_force_legal_followup(
            question=question,
            chat_history=chat_history,
            recent_legal_context=recent_legal_context,
            followup_markers=followup_markers,
        ):
            return "YES"

        recent_text = " ".join(
            (item.get("content") or "").strip()
            for item in (chat_history or [])[-4:]
            if item.get("role") in {"user", "assistant"}
        )
        normalized_recent = self._normalize_text(recent_text)
        if normalized_recent and any(keyword in normalized_recent for keyword in GENERAL_GUARD_KEYWORDS):
            short_follow_up = self._is_short_followup(question)
            if short_follow_up and followup_markers:
                return "YES"
        return "NO"

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return normalized.replace("đ", "d").replace("Đ", "D")
