import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from schema.legal_ingest_schema import LegalIngestSettings
from services.file_extract_service import FileExtractService, FileTextExtractionError, UnsupportedFileTypeError
from services.noidung2_ingest_service import Noidung2IngestService


logger = logging.getLogger("LEGAL_DOCUMENT_ROUTER")


def create_legal_document_router() -> APIRouter:
    settings = LegalIngestSettings.from_env()
    router = APIRouter(prefix="/api/legal-documents", tags=["legal-documents"])
    ingest_service = Noidung2IngestService(settings)

    @router.post("/ingest")
    async def ingest_legal_document(
        file: UploadFile = File(...),
        so_hieu: str = Form(...),
        modified_by: Optional[int] = Form(None),
    ) -> JSONResponse:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise HTTPException(status_code=500, detail="Thieu cau hinh SUPABASE_URL hoac SUPABASE_SERVICE_ROLE_KEY")
        if not settings.openai_api_key:
            raise HTTPException(status_code=500, detail="Thieu cau hinh OPENAI_API_KEY")
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Thieu file upload")
        if not so_hieu.strip():
            raise HTTPException(status_code=400, detail="Truong so_hieu la bat buoc")

        lower_name = file.filename.lower()
        if not any(lower_name.endswith(ext) for ext in FileExtractService.SUPPORTED_EXTENSIONS):
            raise HTTPException(status_code=400, detail="Chi ho tro file .pdf, .docx, .txt")

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="File upload dang rong")
        if len(file_bytes) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File vuot gioi han {settings.max_upload_mb} MB",
            )

        try:
            response = ingest_service.ingest_document(
                file_name=file.filename,
                file_bytes=file_bytes,
                so_hieu=so_hieu.strip(),
                modified_by=modified_by,
            )
            return JSONResponse(content=response.dict())
        except UnsupportedFileTypeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileTextExtractionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("ingest exception")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(exc)},
            )

    return router
