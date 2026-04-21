import logging
from typing import Any, Dict, Optional

from fastapi import UploadFile
from supabase import Client

from config.settings import RAGSettings
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.noidung2_ingest_service import NoiDung2IngestService


logger = logging.getLogger("GLOBAL_DOC_SERVICE")


class GlobalDocService:
    def __init__(
        self,
        *,
        supabase: Client,
        settings: RAGSettings,
        parser_service: DocumentParserService,
        embedding_service: EmbeddingService,
    ) -> None:
        self.noidung2_ingest = NoiDung2IngestService(
            supabase=supabase,
            settings=settings,
            parser_service=parser_service,
            embedding_service=embedding_service,
        )

    def upload_global_document(
        self,
        upload_file: Optional[UploadFile] = None,
        file_bytes: Optional[bytes] = None,
        so_hieu: Optional[str] = None,
        ten_van_ban: Optional[str] = None,
        loai_van_ban: Optional[str] = None,
        trang_thai: Optional[str] = None,
        ngay_ban_hanh: Optional[str] = None,
        ngay_hieu_luc: Optional[str] = None,
        linh_vuc: Optional[str] = None,
        co_quan_ban_hanh: Optional[str] = None,
        uploaded_by: str = "admin",
    ) -> Dict[str, Any]:
        if upload_file is None or not file_bytes:
            raise ValueError("Flow upload file phap ly yeu cau file PDF/DOCX/TXT hop le.")

        logger.info(
            "upload_global_doc received | filename=%s | so_hieu=%s | ten_van_ban=%s",
            upload_file.filename,
            so_hieu or "",
            ten_van_ban or "",
        )
        return self.noidung2_ingest.ingest_document(
            upload_file=upload_file,
            file_bytes=file_bytes,
            uploaded_by=uploaded_by or "admin",
            so_hieu=so_hieu,
            ten_van_ban=ten_van_ban,
            loai_van_ban=loai_van_ban,
            trang_thai=trang_thai,
            ngay_ban_hanh=ngay_ban_hanh,
            ngay_hieu_luc=ngay_hieu_luc,
            linh_vuc=linh_vuc,
            co_quan_ban_hanh=co_quan_ban_hanh,
        )

    def has_global_docs(self) -> bool:
        return self.noidung2_ingest.has_global_docs()

    def deactivate(self, file_id: str) -> int:
        return self.noidung2_ingest.deactivate(file_id)

    def delete(self, file_id: str) -> int:
        return self.noidung2_ingest.delete(file_id)

    def activate(self, file_id: str) -> int:
        return self.noidung2_ingest.activate(file_id)
