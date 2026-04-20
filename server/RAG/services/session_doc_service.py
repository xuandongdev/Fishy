import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import UploadFile
from supabase import Client

from config.settings import RAGSettings
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.noidung2_ingest_service import NoiDung2IngestService


logger = logging.getLogger("SESSION_DOC_SERVICE")


class SessionDocService:
    def __init__(
        self,
        *,
        supabase: Client,
        settings: RAGSettings,
        parser_service: DocumentParserService,
        embedding_service: EmbeddingService,
    ) -> None:
        self.settings = settings
        self.noidung2_ingest = NoiDung2IngestService(
            supabase=supabase,
            settings=settings,
            parser_service=parser_service,
            embedding_service=embedding_service,
        )

    def upload_session_document(self, session_id: str, upload_file: UploadFile, file_bytes: bytes) -> Dict[str, Any]:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.settings.session_doc_ttl_hours)
        logger.info(
            "upload_session_doc received | session_id=%s | filename=%s | expires_at=%s",
            session_id,
            upload_file.filename,
            expires_at.isoformat(),
        )
        result = self.noidung2_ingest.ingest_document(
            upload_file=upload_file,
            file_bytes=file_bytes,
            scope="session",
            uploaded_by="user",
            session_id=session_id,
            expires_at=expires_at,
        )
        result["session_id"] = session_id
        return result

    def cleanup_session(self, session_id: str) -> int:
        return self.noidung2_ingest.cleanup_session(session_id)

    def cleanup_expired(self) -> int:
        return self.noidung2_ingest.cleanup_expired()

    def has_session_docs(self, session_id: str) -> bool:
        return self.noidung2_ingest.has_session_docs(session_id)
