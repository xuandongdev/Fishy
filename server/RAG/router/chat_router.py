import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from langchain_adapter import LangChainAdapter
from services.retrieval_service import RetrievalService

logger = logging.getLogger("CHAT_ROUTER")


class ChatAskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = []


def create_chat_router(
    retrieval_service: RetrievalService,
    langchain_adapter: Optional[LangChainAdapter] = None,
) -> APIRouter:
    router = APIRouter()

    async def handle_question(req: ChatAskRequest) -> Dict[str, Any]:
        if langchain_adapter is not None:
            return await langchain_adapter.chat(
                question=req.question,
                session_id=req.session_id,
                chat_history=req.history,
            )

        retrieval = retrieval_service.retrieve_context(
            question=req.question,
            original_question=req.question,
            effective_question=req.question,
            history=req.history or [],
        )
        final_hits = retrieval.get("combined_results", [])
        answer_bundle = retrieval_service.answer_service.generate_answer(
            req.question,
            final_hits,
            history=req.history or [],
            effective_question=retrieval.get("effective_question") or req.question,
            debug_meta={
                "vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
                "query_km": retrieval.get("query_km"),
            },
        )
        return {
            "success": True,
            "answer": answer_bundle["answer"],
            "route": "legal_rag",
            "session_id": req.session_id,
            "used_fallback": retrieval["used_fallback"],
            "used_firecrawl": retrieval["firecrawl_called"],
            "sources": answer_bundle["sources"],
            "debug": {
                "legal_results": len(retrieval["legal_results"]),
                "trusted_cache_results": len(retrieval["trusted_cache_results"]),
                "candidate_results": len(retrieval["candidate_results"]),
                "final_hits": len(retrieval["combined_results"]),
                "firecrawl_called": retrieval["firecrawl_called"],
                "searched_sources_count": retrieval["searched_sources_count"],
                "scraped_urls_count": retrieval["scraped_urls_count"],
                "firecrawl_cached": retrieval["firecrawl_cached"],
                "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
                "query_km": retrieval.get("query_km"),
                "effective_question": retrieval.get("effective_question"),
            },
            "meta": {
                "used_legal_retrieval": True,
                "source_count": len(answer_bundle["sources"]),
                "retrieval_time_ms": retrieval.get("retrieval_time_ms", 0.0),
                "rerank_time_ms": retrieval.get("rerank_time_ms", 0.0),
                "gen_time_ms": 0.0,
                "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
                "effective_question": retrieval.get("effective_question"),
                "query_km": retrieval.get("query_km"),
            },
        }

    @router.post("/api/chat/ask")
    async def ask_question(req: ChatAskRequest) -> Dict[str, Any]:
        return await handle_question(req)

    @router.post("/chat")
    async def ask_question_alias(req: ChatAskRequest) -> Dict[str, Any]:
        return await handle_question(req)

    return router
