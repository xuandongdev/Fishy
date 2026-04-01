import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.retrieval_service import RetrievalService


logger = logging.getLogger("CHAT_ROUTER")


class ChatAskRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = []


def create_chat_router(retrieval_service: RetrievalService) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.post("/ask")
    async def ask_question(req: ChatAskRequest) -> Dict[str, Any]:
        retrieval = retrieval_service.retrieve_context(req.question)
        final_hits = retrieval["combined_results"]

        if not final_hits:
            return {
                "success": True,
                "answer": "Chua tim thay du du lieu dang tin cay trong legal_db, trusted cache, hoac Firecrawl de tra loi cau hoi nay.",
                "used_fallback": retrieval["used_fallback"],
                "sources": [],
                "debug": {
                    "legal_results": len(retrieval["legal_results"]),
                    "trusted_cache_results": len(retrieval["trusted_cache_results"]),
                    "firecrawl_called": retrieval["firecrawl_called"],
                    "firecrawl_cached": retrieval["firecrawl_cached"],
                },
            }

        answer_bundle = retrieval_service.answer_service.generate_answer(req.question, final_hits)
        return {
            "success": True,
            "answer": answer_bundle["answer"],
            "used_fallback": retrieval["used_fallback"],
            "sources": answer_bundle["sources"],
            "debug": {
                "legal_results": len(retrieval["legal_results"]),
                "trusted_cache_results": len(retrieval["trusted_cache_results"]),
                "firecrawl_called": retrieval["firecrawl_called"],
                "firecrawl_cached": retrieval["firecrawl_cached"],
            },
        }

    return router
