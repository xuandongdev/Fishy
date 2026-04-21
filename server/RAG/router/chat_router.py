import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from langchain_adapter import LangChainAdapter
from services.global_doc_service import GlobalDocService
from services.retrieval_service import RetrievalService

logger = logging.getLogger("CHAT_ROUTER")


class ChatAskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = []


def create_chat_router(
    retrieval_service: RetrievalService,
    langchain_adapter: Optional[LangChainAdapter] = None,
    global_doc_service: Optional[GlobalDocService] = None,
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
            session_id=req.session_id,  # giu lai cho chat/history, khong dung cho session docs
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
            "sources": answer_bundle["sources"],
            "debug": {
                "used_global_docs": retrieval.get("used_global_docs", False),
                "global_doc_hits": retrieval.get("global_doc_hits", 0),
                "global_doc_top_score": retrieval.get("global_doc_top_score", 0.0),
                "legal_results": len(retrieval["legal_results"]),
                "candidate_results": len(retrieval["candidate_results"]),
                "final_hits": len(retrieval["combined_results"]),
                "detected_vehicle_type": retrieval.get("detected_vehicle_type", "khac"),
                "query_km": retrieval.get("query_km"),
                "effective_question": retrieval.get("effective_question"),
            },
            "meta": {
                "used_legal_retrieval": True,
                "used_global_docs": retrieval.get("used_global_docs", False),
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

    @router.post("/upload-global-doc")
    async def upload_global_doc(
        file: Optional[UploadFile] = File(default=None),
        so_hieu: Optional[str] = Form(default=None),
        ten_van_ban: Optional[str] = Form(default=None),
        loai_van_ban: Optional[str] = Form(default=None),
        trang_thai: Optional[str] = Form(default=None),
        ngay_ban_hanh: Optional[str] = Form(default=None),
        ngay_hieu_luc: Optional[str] = Form(default=None),
        linh_vuc: Optional[str] = Form(default=None),
        co_quan_ban_hanh: Optional[str] = Form(default=None),
        uploaded_by: str = Form(default="admin"),
    ) -> Dict[str, Any]:
        if global_doc_service is None:
            raise HTTPException(status_code=503, detail="Global document upload chua duoc khoi tao.")

        file_bytes: Optional[bytes] = None
        if file is not None:
            file_name = (file.filename or "").strip()
            if not file_name:
                raise HTTPException(status_code=400, detail="Thieu ten file upload.")
            lowered = file_name.lower()
            if not (lowered.endswith(".pdf") or lowered.endswith(".docx") or lowered.endswith(".txt")):
                raise HTTPException(status_code=400, detail="Chi ho tro file .pdf, .docx hoac .txt")
            file_bytes = await file.read()
            if not file_bytes:
                raise HTTPException(status_code=400, detail="File upload dang rong")

        try:
            return global_doc_service.upload_global_document(
                upload_file=file,
                file_bytes=file_bytes,
                so_hieu=so_hieu,
                ten_van_ban=ten_van_ban,
                loai_van_ban=loai_van_ban,
                trang_thai=trang_thai,
                ngay_ban_hanh=ngay_ban_hanh,
                ngay_hieu_luc=ngay_hieu_luc,
                linh_vuc=linh_vuc,
                co_quan_ban_hanh=co_quan_ban_hanh,
                uploaded_by=uploaded_by or "admin",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("upload global doc exception")
            raise HTTPException(status_code=500, detail=f"Khong the lap chi muc tai lieu dung chung: {exc}") from exc

    @router.post("/global-docs/{file_id}/deactivate")
    async def deactivate_global_doc(file_id: str) -> Dict[str, Any]:
        if global_doc_service is None:
            raise HTTPException(status_code=503, detail="Global document service chua duoc khoi tao.")
        affected = global_doc_service.deactivate(file_id)
        return {"success": True, "file_id": file_id, "affected": affected}

    @router.post("/global-docs/{file_id}/activate")
    async def activate_global_doc(file_id: str) -> Dict[str, Any]:
        if global_doc_service is None:
            raise HTTPException(status_code=503, detail="Global document service chua duoc khoi tao.")
        affected = global_doc_service.activate(file_id)
        return {"success": True, "file_id": file_id, "affected": affected}

    @router.delete("/global-docs/{file_id}")
    async def delete_global_doc(file_id: str) -> Dict[str, Any]:
        if global_doc_service is None:
            raise HTTPException(status_code=503, detail="Global document service chua duoc khoi tao.")
        affected = global_doc_service.delete(file_id)
        return {"success": True, "file_id": file_id, "affected": affected}

    return router
