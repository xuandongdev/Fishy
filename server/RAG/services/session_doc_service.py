import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import UploadFile

from config.settings import RAGSettings
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService


logger = logging.getLogger("SESSION_DOC_SERVICE")


class SessionDocService:
    def __init__(
        self,
        settings: RAGSettings,
        parser_service: DocumentParserService,
        embedding_service: EmbeddingService,
        qdrant_service: QdrantService,
    ) -> None:
        self.settings = settings
        self.parser_service = parser_service
        self.embedding_service = embedding_service
        self.qdrant_service = qdrant_service

    def upload_session_document(self, session_id: str, upload_file: UploadFile, file_bytes: bytes) -> Dict[str, Any]:
        file_name = (upload_file.filename or "uploaded_document").strip()
        parsed = self.parser_service.parse_document(file_name, file_bytes)
        text = parsed["text"]
        doc_type = parsed["doc_type"]
        sections = list(parsed.get("sections") or [])
        chunking_mode = str(parsed.get("chunking_mode") or "flat_fallback")
        sections_count = int(parsed.get("sections_count") or len(sections))
        file_id = str(uuid.uuid4())

        logger.info("upload received | session_id=%s | filename=%s | doc_type=%s", session_id, file_name, doc_type)
        logger.info("document parsed | session_id=%s | text_length=%s", session_id, len(text))
        logger.info(
            "document chunking plan | session_id=%s | chunking_mode=%s | sections_count=%s",
            session_id,
            chunking_mode,
            sections_count,
        )

        chunks = self._chunk_sections(sections) if sections else self._chunk_text(text)
        vectors = self.embedding_service.generate_passage_embeddings([chunk["content"] for chunk in chunks])

        uploaded_at = datetime.now(timezone.utc)
        expires_at = uploaded_at + timedelta(hours=self.settings.session_doc_ttl_hours)
        payload_rows: List[Dict[str, Any]] = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            payload_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "vector": vector,
                    "payload": {
                        "session_id": session_id,
                        "file_id": file_id,
                        "filename": file_name,
                        "chunk_index": index,
                        "section_path": chunk.get("section_path") or "Toan van",
                        "page_start": chunk.get("page_start"),
                        "page_end": chunk.get("page_end"),
                        "source_type": "user_upload",
                        "doc_type": doc_type,
                        "uploaded_at": uploaded_at.isoformat(),
                        "expires_at": expires_at.isoformat(),
                        "content": chunk["content"],
                    },
                }
            )

        indexed_count = self.qdrant_service.upsert_session_chunks(payload_rows)
        logger.info(
            "session doc indexed | session_id=%s | chunking_mode=%s | sections_count=%s | chunks_created=%s | qdrant_upsert_count=%s",
            session_id,
            chunking_mode,
            sections_count,
            len(chunks),
            indexed_count,
        )
        return {
            "success": True,
            "session_id": session_id,
            "file_id": file_id,
            "filename": file_name,
            "doc_type": doc_type,
            "chunks_indexed": indexed_count,
            "message": "Tai lieu da duoc lap chi muc cho phien chat.",
        }

    def cleanup_session(self, session_id: str) -> int:
        return self.qdrant_service.delete_session_docs(session_id)

    def cleanup_expired(self) -> int:
        return self.qdrant_service.delete_expired_docs()

    def has_session_docs(self, session_id: str) -> bool:
        return self.qdrant_service.has_session_docs(session_id)

    def _chunk_text(self, text: str) -> List[Dict[str, Any]]:
        chunk_size = max(300, self.settings.session_doc_chunk_size)
        overlap = max(0, min(self.settings.session_doc_chunk_overlap, chunk_size // 3))
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        chunks: List[Dict[str, Any]] = []
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + chunk_size)
            candidate = normalized[start:end]
            if end < len(normalized):
                split_candidates = [candidate.rfind("\n\n"), candidate.rfind("\n"), candidate.rfind(". ")]
                split_at = max(split_candidates)
                if split_at > int(chunk_size * 0.55):
                    end = start + split_at + 1
                    candidate = normalized[start:end]
            content = candidate.strip()
            if len(content) >= 80:
                chunks.append(
                    {
                        "content": content,
                        "section_path": "Toan van",
                        "page_start": 1,
                        "page_end": None,
                    }
                )
            if end >= len(normalized):
                break
            start = max(start + 1, end - overlap)
        if not chunks:
            chunks.append({"content": normalized[:chunk_size], "section_path": "Toan van", "page_start": 1, "page_end": None})
        return chunks

    def _chunk_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        chunk_size = max(300, self.settings.session_doc_chunk_size)
        overlap = max(0, min(self.settings.session_doc_chunk_overlap, chunk_size // 3))

        for section in sections:
            section_content = str(section.get("content") or "").strip()
            if len(section_content) <= chunk_size:
                chunks.append(
                    {
                        "content": section_content,
                        "section_path": section.get("section_path") or "Toan van",
                        "page_start": section.get("page_start"),
                        "page_end": section.get("page_end"),
                    }
                )
                continue

            start = 0
            while start < len(section_content):
                end = min(len(section_content), start + chunk_size)
                candidate = section_content[start:end]
                if end < len(section_content):
                    split_candidates = [candidate.rfind("\n\n"), candidate.rfind("\n"), candidate.rfind(". ")]
                    split_at = max(split_candidates)
                    if split_at > int(chunk_size * 0.55):
                        end = start + split_at + 1
                        candidate = section_content[start:end]
                content = candidate.strip()
                if len(content) >= 80:
                    chunks.append(
                        {
                            "content": content,
                            "section_path": section.get("section_path") or "Toan van",
                            "page_start": section.get("page_start"),
                            "page_end": section.get("page_end"),
                        }
                    )
                if end >= len(section_content):
                    break
                start = max(start + 1, end - overlap)
        return chunks
