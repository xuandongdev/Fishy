import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from config.settings import RAGSettings
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.qdrant_service import QdrantService


logger = logging.getLogger("GLOBAL_DOC_SERVICE")


class GlobalDocService:
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
        manual_metadata = self._normalize_manual_metadata(
            so_hieu=so_hieu,
            ten_van_ban=ten_van_ban,
            loai_van_ban=loai_van_ban,
            trang_thai=trang_thai,
            ngay_ban_hanh=ngay_ban_hanh,
            ngay_hieu_luc=ngay_hieu_luc,
            linh_vuc=linh_vuc,
            co_quan_ban_hanh=co_quan_ban_hanh,
        )
        has_manual_metadata = any(value for value in manual_metadata.values())
        has_file = upload_file is not None and bool(file_bytes)
        if not has_manual_metadata and not has_file:
            raise ValueError("Request phai co metadata hop le hoac file PDF/DOCX.")

        file_name = ((upload_file.filename if upload_file else "") or "metadata_only").strip()
        doc_type = "metadata"
        sections: List[Dict[str, Any]] = []
        chunking_mode = "metadata_only"
        sections_count = 0
        parsed_text = ""
        parser_metadata: Dict[str, Optional[str]] = {}
        metadata_merge_mode = "manual_only"

        if has_file and upload_file is not None and file_bytes is not None:
            parsed = self.parser_service.parse_document(file_name, file_bytes)
            doc_type = parsed["doc_type"]
            sections = list(parsed.get("sections") or [])
            chunking_mode = str(parsed.get("chunking_mode") or "flat_fallback")
            sections_count = int(parsed.get("sections_count") or len(sections))
            parsed_text = str(parsed.get("text") or "")
            parser_metadata = self._extract_legal_metadata(
                title=file_name,
                filename=file_name,
                section_path=" > ".join(str(section.get("section_path") or "") for section in sections[:3]),
                content=parsed_text[:2400],
            )
            metadata_merge_mode = "manual_plus_file" if has_manual_metadata else "file_only"

        file_id = str(uuid.uuid4())
        merged_metadata = self._merge_metadata(
            manual_metadata=manual_metadata,
            parser_metadata=parser_metadata,
            file_name=file_name,
        )

        logger.info(
            "upload_global_doc received | filename=%s | has_file=%s | has_manual_metadata=%s | metadata_merge_mode=%s",
            file_name,
            has_file,
            has_manual_metadata,
            metadata_merge_mode,
        )
        logger.info("upload_global_doc parsed | parsed_text_length=%s", len(parsed_text))

        chunks = self._chunk_sections(sections) if sections else [self._build_metadata_only_chunk(merged_metadata)]
        vectors = self.embedding_service.generate_passage_embeddings([chunk["content"] for chunk in chunks])

        uploaded_at = datetime.now(timezone.utc).isoformat()
        payload_rows: List[Dict[str, Any]] = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            legal_meta = self._extract_legal_metadata(
                title=merged_metadata.get("ten_van_ban") or file_name,
                filename=file_name,
                section_path=str(chunk.get("section_path") or ""),
                content=str(chunk.get("content") or ""),
            )
            final_metadata = {**legal_meta, **{k: v for k, v in merged_metadata.items() if v}}
            payload_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "vector": vector,
                    "payload": {
                        "scope": "global",
                        "source_type": "admin_upload",
                        "file_id": file_id,
                        "filename": file_name,
                        "title": merged_metadata.get("ten_van_ban") or file_name,
                        "ten_van_ban": merged_metadata.get("ten_van_ban") or file_name,
                        "uploaded_by": uploaded_by,
                        "doc_type": doc_type,
                        "chunk_index": index,
                        "section_path": chunk.get("section_path") or "Toan van",
                        "page_start": chunk.get("page_start"),
                        "page_end": chunk.get("page_end"),
                        "uploaded_at": uploaded_at,
                        "is_active": True,
                        "content": chunk["content"],
                        **final_metadata,
                    },
                }
            )

        qdrant_upsert_count = self.qdrant_service.upsert_global_chunks(payload_rows)
        logger.info(
            "upload_global_doc indexed | sections_count=%s | chunking_mode=%s | chunks_created=%s | qdrant_upsert_count=%s",
            sections_count,
            chunking_mode,
            len(chunks),
            qdrant_upsert_count,
        )
        return {
            "success": True,
            "file_id": file_id,
            "filename": file_name,
            "title": merged_metadata.get("ten_van_ban") or file_name,
            "ten_van_ban": merged_metadata.get("ten_van_ban") or file_name,
            "chunks_indexed": qdrant_upsert_count,
            "chunking_mode": chunking_mode,
            "sections_count": sections_count,
            "message": "Tai lieu da duoc lap chi muc vao kho tri thuc dung chung.",
        }

    def has_global_docs(self) -> bool:
        return self.qdrant_service.has_global_docs()

    def deactivate(self, file_id: str) -> int:
        return self.qdrant_service.deactivate_global_doc(file_id)

    def delete(self, file_id: str) -> int:
        return self.qdrant_service.delete_global_doc(file_id)

    def activate(self, file_id: str) -> int:
        return self.qdrant_service.activate_global_doc(file_id)

    def _chunk_sections(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunk_size = max(300, self.settings.session_doc_chunk_size)
        overlap = max(0, min(self.settings.session_doc_chunk_overlap, chunk_size // 3))
        chunks: List[Dict[str, Any]] = []

        if not sections:
            return []

        for section in sections:
            content = str(section.get("content") or "").strip()
            if not content:
                continue
            if len(content) <= chunk_size:
                chunks.append(
                    {
                        "content": content,
                        "section_path": section.get("section_path") or "Toan van",
                        "page_start": section.get("page_start"),
                        "page_end": section.get("page_end"),
                    }
                )
                continue

            start = 0
            while start < len(content):
                end = min(len(content), start + chunk_size)
                candidate = content[start:end]
                if end < len(content):
                    split_candidates = [candidate.rfind("\n\n"), candidate.rfind("\n"), candidate.rfind(". ")]
                    split_at = max(split_candidates)
                    if split_at > int(chunk_size * 0.55):
                        end = start + split_at + 1
                        candidate = content[start:end]
                piece = candidate.strip()
                if len(piece) >= 80:
                    chunks.append(
                        {
                            "content": piece,
                            "section_path": section.get("section_path") or "Toan van",
                            "page_start": section.get("page_start"),
                            "page_end": section.get("page_end"),
                        }
                    )
                if end >= len(content):
                    break
                start = max(start + 1, end - overlap)
        return chunks

    def _build_metadata_only_chunk(self, metadata: Dict[str, Optional[str]]) -> Dict[str, Any]:
        lines = []
        for label, key in [
            ("Ten van ban", "ten_van_ban"),
            ("So hieu", "so_hieu"),
            ("Loai van ban", "loai_van_ban"),
            ("Trang thai", "trang_thai"),
            ("Ngay ban hanh", "ngay_ban_hanh"),
            ("Ngay hieu luc", "ngay_hieu_luc"),
            ("Linh vuc", "linh_vuc"),
            ("Co quan ban hanh", "co_quan_ban_hanh"),
        ]:
            value = (metadata.get(key) or "").strip()
            if value:
                lines.append(f"{label}: {value}")
        content = "\n".join(lines).strip()
        if not content:
            raise ValueError("Khong co du lieu de lap chi muc tai lieu toan cuc.")
        return {
            "content": content,
            "section_path": "Thong tin tong quan",
            "page_start": None,
            "page_end": None,
        }

    def _normalize_manual_metadata(
        self,
        so_hieu: Optional[str],
        ten_van_ban: Optional[str],
        loai_van_ban: Optional[str],
        trang_thai: Optional[str],
        ngay_ban_hanh: Optional[str],
        ngay_hieu_luc: Optional[str],
        linh_vuc: Optional[str],
        co_quan_ban_hanh: Optional[str],
    ) -> Dict[str, Optional[str]]:
        return {
            "so_hieu": (so_hieu or "").strip() or None,
            "ten_van_ban": (ten_van_ban or "").strip() or None,
            "loai_van_ban": (loai_van_ban or "").strip() or None,
            "trang_thai": (trang_thai or "").strip() or None,
            "ngay_ban_hanh": (ngay_ban_hanh or "").strip() or None,
            "ngay_hieu_luc": (ngay_hieu_luc or "").strip() or None,
            "linh_vuc": (linh_vuc or "").strip() or None,
            "co_quan_ban_hanh": (co_quan_ban_hanh or "").strip() or None,
        }

    def _merge_metadata(
        self,
        manual_metadata: Dict[str, Optional[str]],
        parser_metadata: Dict[str, Optional[str]],
        file_name: str,
    ) -> Dict[str, Optional[str]]:
        merged = dict(parser_metadata)
        merged.update({key: value for key, value in manual_metadata.items() if value})
        merged["ten_van_ban"] = merged.get("ten_van_ban") or self._filename_title(file_name)
        merged["so_hieu"] = merged.get("so_hieu") or parser_metadata.get("so_hieu")
        return merged

    def _filename_title(self, file_name: str) -> str:
        return re.sub(r"\.(pdf|docx)$", "", file_name, flags=re.I).replace("_", " ").strip()

    def _extract_legal_metadata(
        self,
        title: str,
        filename: str,
        section_path: str,
        content: str,
    ) -> Dict[str, Optional[str]]:
        probe = " ".join(part for part in [title, filename, section_path, content[:1200]] if part)
        normalized = probe.lower()

        so_hieu_match = re.search(r"\b\d{1,4}/\d{4}(?:/[a-z0-9\-]+)?\b", normalized, re.I)
        chapter_match = re.search(r"(chương\s+[ivxlcdm0-9]+)", section_path, re.I)
        muc_match = re.search(r"(mục\s+[0-9ivxlcdm]+)", section_path, re.I)
        dieu_match = re.search(r"(điều|dieu)\s+(\d+[a-z]?)", section_path, re.I)
        khoan_match = re.search(r"(khoản|khoan)\s+(\d+[a-z]?)", probe, re.I)
        diem_match = re.search(r"(điểm|diem)\s+([a-z0-9]+)", probe, re.I)

        loai_van_ban = None
        for candidate in ["nghị định", "nghi dinh", "luật", "luat", "thông tư", "thong tu", "quyết định", "quyet dinh"]:
            if candidate in normalized:
                loai_van_ban = candidate
                break
        if loai_van_ban in {"nghi dinh"}:
            loai_van_ban = "nghị định"
        if loai_van_ban in {"luat"}:
            loai_van_ban = "luật"
        if loai_van_ban in {"thong tu"}:
            loai_van_ban = "thông tư"
        if loai_van_ban in {"quyet dinh"}:
            loai_van_ban = "quyết định"

        return {
            "so_hieu": so_hieu_match.group(0).upper() if so_hieu_match else None,
            "loai_van_ban": loai_van_ban,
            "chapter": chapter_match.group(1) if chapter_match else None,
            "muc": muc_match.group(1) if muc_match else None,
            "dieu": dieu_match.group(2) if dieu_match else None,
            "khoan": khoan_match.group(2) if khoan_match else None,
            "diem": diem_match.group(2) if diem_match else None,
        }
