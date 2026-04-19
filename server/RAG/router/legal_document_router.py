from fastapi import APIRouter, HTTPException


def create_legal_document_router() -> APIRouter:
    router = APIRouter(prefix="/api/legal-documents", tags=["legal-documents"])

    @router.post("/ingest")
    async def ingest_legal_document() -> None:
        raise HTTPException(
            status_code=410,
            detail="Legal ingest legacy da bi vo hieu hoa. Hay dung upload global docs tren RAG API.",
        )

    return router
