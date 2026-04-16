import logging
import time
import unicodedata
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from config.settings import RAGSettings
from services.answer_service import AnswerService
from services.conversation_manager import ConversationManager
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

    async def chat(
        self,
        question: str,
        session_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        active_session_id = session_id or str(uuid.uuid4())
        history = self._build_history(active_session_id, chat_history)
        route = self.route_question(question)
        start_time = time.perf_counter()

        logger.info("chat incoming | session_id=%s | route=%s | question=%s", active_session_id, route, question[:200])

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
        retrieval = self.retrieval_service.retrieve_context(question)
        final_hits = retrieval["combined_results"]

        if not final_hits:
            logger.info("legal route no context | session_id=%s | firecrawl=%s", session_id, retrieval["firecrawl_called"])
            return {
                "success": True,
                "answer": "Chua tim thay du du lieu dang tin cay trong legal_db, trusted cache, hoac Firecrawl de tra loi cau hoi nay.",
                "sources": [],
                "used_fallback": retrieval["used_fallback"],
                "used_firecrawl": retrieval["firecrawl_called"],
                "evaluation": self._build_evaluation_payload(
                    final_hits=final_hits,
                    candidate_hits=retrieval.get("candidate_results", []),
                    timings={
                        "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                        "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                        "gen_time_ms": 0.0,
                    },
                    detected_vehicle_type=retrieval.get("detected_vehicle_type", "khac"),
                ),
                "debug": self._build_debug_info(retrieval, branch="legal_rag"),
                "meta": {
                    "used_legal_retrieval": True,
                    "source_count": 0,
                    "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                    "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                    "gen_time_ms": 0.0,
                    "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
                },
            }

        gen_start = time.perf_counter()
        answer_bundle = self.answer_service.generate_answer(question, final_hits, history=history)
        gen_time_ms = round((time.perf_counter() - gen_start) * 1000, 2)
        logger.info("legal answer generated | session_id=%s | answer=%s", session_id, answer_bundle["answer"][:500])
        return {
            "success": True,
            "answer": answer_bundle["answer"],
            "sources": answer_bundle["sources"],
            "used_fallback": retrieval["used_fallback"],
            "used_firecrawl": retrieval["firecrawl_called"],
            "evaluation": self._build_evaluation_payload(
                final_hits=final_hits,
                candidate_hits=retrieval.get("candidate_results", []),
                timings={
                    "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                    "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                    "gen_time_ms": gen_time_ms,
                },
                detected_vehicle_type=retrieval.get("detected_vehicle_type", "khac"),
            ),
            "debug": self._build_debug_info(retrieval, branch="legal_rag"),
            "meta": {
                "used_legal_retrieval": True,
                "source_count": len(answer_bundle["sources"]),
                "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                "gen_time_ms": gen_time_ms,
                "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
            },
        }

    async def handle_general(self, question: str, session_id: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        logger.info("general route start | session_id=%s", session_id)
        lc_history = self._to_langchain_messages(history)
        chain = self.general_chat_prompt | self.general_chat_model
        response = await chain.ainvoke({"question": question, "history": lc_history})
        answer = response.content if hasattr(response, "content") else str(response)
        logger.info("general answer generated | session_id=%s | answer=%s", session_id, answer[:500])
        return {
            "success": True,
            "answer": answer,
            "sources": [],
            "used_fallback": False,
            "used_firecrawl": False,
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
            },
            "meta": {
                "used_legal_retrieval": False,
                "source_count": 0,
            },
        }

    def _build_history(self, session_id: str, chat_history: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
        if chat_history:
            return [item for item in chat_history if item.get("role") in {"user", "assistant"} and item.get("content")]
        return self.conversation_manager.get_history(session_id)

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

    def _build_debug_info(self, retrieval: Dict[str, Any], branch: str) -> Dict[str, Any]:
        return {
            "branch": branch,
            "legal_results": len(retrieval["legal_results"]),
            "trusted_cache_results": len(retrieval["trusted_cache_results"]),
            "candidate_results": len(retrieval.get("candidate_results", [])),
            "final_hits": len(retrieval.get("combined_results", [])),
            "firecrawl_called": retrieval["firecrawl_called"],
            "searched_sources_count": retrieval["searched_sources_count"],
            "scraped_urls_count": retrieval["scraped_urls_count"],
            "firecrawl_cached": retrieval["firecrawl_cached"],
            "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
        }

    def _build_evaluation_payload(
        self,
        final_hits: List[Dict[str, Any]],
        candidate_hits: Optional[List[Dict[str, Any]]] = None,
        timings: Optional[Dict[str, Any]] = None,
        detected_vehicle_type: str = "khac",
    ) -> Dict[str, Any]:
        def normalize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            normalized_hits: List[Dict[str, Any]] = []
            for item in items:
                normalized_hits.append(
                    {
                        "primary_id": item.get("primary_id"),
                        "label": item.get("label"),
                        "content": item.get("content"),
                        "url": item.get("url"),
                        "source_type": item.get("source_type"),
                        "vehicle_type": item.get("vehicle_type"),
                        "hybrid_score": item.get("hybrid_score"),
                        "rerank_score": item.get("rerank_score"),
                    }
                )
            return normalized_hits

        return {
            "detected_vehicle_type": detected_vehicle_type,
            "candidate_hits": normalize(candidate_hits or []),
            "hits": normalize(final_hits),
            "timings": timings or {},
        }

    def _normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
