import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from supabase import Client

from config.settings import RAGSettings
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService


logger = logging.getLogger("NOIDUNG2_INGEST_SERVICE")


class NoiDung2IngestService:
    def __init__(
        self,
        *,
        supabase: Client,
        settings: RAGSettings,
        parser_service: DocumentParserService,
        embedding_service: EmbeddingService,
    ) -> None:
        self.supabase = supabase
        self.settings = settings
        self.parser_service = parser_service
        self.embedding_service = embedding_service

    def ingest_document(
        self,
        *,
        upload_file: UploadFile,
        file_bytes: bytes,
        scope: str,
        uploaded_by: str,
        so_hieu: Optional[str] = None,
        ten_van_ban: Optional[str] = None,
        loai_van_ban: Optional[str] = None,
        trang_thai: Optional[str] = None,
        ngay_ban_hanh: Optional[str] = None,
        ngay_hieu_luc: Optional[str] = None,
        linh_vuc: Optional[str] = None,
        co_quan_ban_hanh: Optional[str] = None,
        session_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        file_name = (upload_file.filename or "uploaded_legal_document").strip()
        parsed = self.parser_service.parse_document(file_name, file_bytes)
        nodes = list(parsed.get("nodes") or [])
        if not nodes:
            raise ValueError("Khong nhan dien duoc node phap ly hop le de luu vao noidung2.")

        now = datetime.now(timezone.utc)
        active_file_id = str(uuid.uuid4())
        normalized_so_hieu = (so_hieu or self._guess_so_hieu(file_name)).strip() or None
        normalized_title = (ten_van_ban or self._guess_title(file_name)).strip() or file_name
        source_file_type = str(parsed.get("doc_type") or self._guess_extension(file_name) or "unknown")
        doc_type = "session_upload" if scope == "session" else "global_upload"
        shared_metadata = {
            "scope": scope,
            "session_id": session_id,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "loai_van_ban": loai_van_ban,
            "trang_thai": trang_thai,
            "ngay_ban_hanh": ngay_ban_hanh,
            "ngay_hieu_luc": ngay_hieu_luc,
            "linh_vuc": linh_vuc,
            "co_quan_ban_hanh": co_quan_ban_hanh,
            "chunking_mode": parsed.get("chunking_mode"),
            "source_filename": file_name,
        }

        inserted_refs: Dict[str, int] = {}
        inserted_count = 0
        validated_count = 0
        preview: List[Dict[str, Any]] = []

        for chunk_index, node in enumerate(nodes):
            node_ref = str(node.get("node_ref") or f"NODE-{chunk_index + 1}")
            parent_ref = str(node.get("parent_ref") or "").strip() or None
            is_validated = bool(node.get("is_validated"))
            if is_validated:
                validated_count += 1

            search_text = self._build_search_text(
                title=normalized_title,
                so_hieu=normalized_so_hieu,
                section_path=str(node.get("section_path") or ""),
                content=str(node.get("noidung") or ""),
                rela=list(node.get("rela") or []),
            )
            embedding = self.embedding_service.generate_passage_embedding(search_text) if is_validated else None
            rela = list(node.get("rela") or [])
            rela_embed = self.embedding_service.generate_rela_embedding(str(node.get("noidung") or ""), rela) if is_validated and rela else None

            row = {
                "sohieu": normalized_so_hieu,
                "noidung": str(node.get("noidung") or "").strip(),
                "sothutund_cha": inserted_refs.get(parent_ref) if parent_ref else None,
                "search_text": search_text,
                "modified_by": uploaded_by,
                "modified_at": now.isoformat(),
                "embedding": embedding,
                "loai_muc": node.get("loai_muc"),
                "ky_hieu": node.get("ky_hieu"),
                "thu_tu": node.get("thu_tu"),
                "rela": rela or None,
                "rela_embed": rela_embed,
                "min_km": node.get("min_km"),
                "max_km": node.get("max_km"),
                "ten_van_ban": normalized_title,
                "source_file_name": file_name,
                "source_file_type": source_file_type,
                "doc_type": doc_type,
                "file_id": active_file_id,
                "chunk_index": chunk_index,
                "section_path": node.get("section_path"),
                "page_start": node.get("page_start"),
                "page_end": node.get("page_end"),
                "raw_text": node.get("raw_text") or node.get("noidung"),
                "extracted_json": {
                    "node_ref": node_ref,
                    "parent_ref": parent_ref,
                    "chapter": node.get("chapter"),
                    "muc": node.get("muc"),
                    "dieu": node.get("dieu"),
                    "khoan": node.get("khoan"),
                    "diem": node.get("diem"),
                },
                "metadata": {key: value for key, value in shared_metadata.items() if value not in {None, ""}},
                "is_validated": is_validated,
                "validation_errors": list(node.get("validation_errors") or []),
                "is_active": True,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            self.supabase.table("noidung2").insert(row).execute()

            fetch_response = (
                self.supabase.table("noidung2")
                .select("sothutund")
                .eq("file_id", active_file_id)
                .eq("chunk_index", chunk_index)
                .order("sothutund", desc=True)
                .limit(1)
                .execute()
            )

            fetch_rows = fetch_response.data or []
            if not fetch_rows:
                raise RuntimeError(
                    f"Da insert noidung2 nhung khong lay duoc sothutund cho node_ref={node_ref}, chunk_index={chunk_index}"
                )

            inserted_id = int(fetch_rows[0]["sothutund"])
            inserted_refs[node_ref] = inserted_id
            inserted_count += 1
            preview.append(
                {
                    "segment_ref": node_ref,
                    "loai_muc": node.get("loai_muc"),
                    "ky_hieu": node.get("ky_hieu"),
                    "thu_tu": node.get("thu_tu"),
                    "noidung": str(node.get("noidung") or "")[:300],
                    "parent_ref": parent_ref,
                    "inserted_id": inserted_id,
                    "is_validated": is_validated,
                    "validation_errors": list(node.get("validation_errors") or []),
                }
            )

        logger.info(
            "noidung2 ingest completed | scope=%s | file_id=%s | nodes=%s | validated=%s | inserted=%s",
            scope,
            active_file_id,
            len(nodes),
            validated_count,
            inserted_count,
        )
        return {
            "success": True,
            "file_id": active_file_id,
            "filename": file_name,
            "title": normalized_title,
            "ten_van_ban": normalized_title,
            "chunks_indexed": sum(1 for item in preview if item["is_validated"]),
            "inserted_count": inserted_count,
            "sections_count": int(parsed.get("sections_count") or 0),
            "chunking_mode": parsed.get("chunking_mode"),
            "validated_count": validated_count,
            "preview": preview[:20],
            "message": "Tai lieu da duoc luu vao noidung2.",
        }

    def has_global_docs(self) -> bool:
        rows = (
            self.supabase.table("noidung2")
            .select("sothutund, metadata, is_active, is_validated")
            .eq("is_active", True)
            .eq("is_validated", True)
            .limit(100)
            .execute()
            .data
            or []
        )
        return any((row.get("metadata") or {}).get("scope") != "session" for row in rows)

    def activate(self, file_id: str) -> int:
        return self._update_file_active_state(file_id=file_id, is_active=True)

    def deactivate(self, file_id: str) -> int:
        return self._update_file_active_state(file_id=file_id, is_active=False)

    def delete(self, file_id: str) -> int:
        response = self.supabase.table("noidung2").delete().eq("file_id", file_id).execute()
        return len(response.data or [])

    def has_session_docs(self, session_id: str) -> bool:
        rows = (
            self.supabase.table("noidung2")
            .select("sothutund, metadata, is_active, is_validated")
            .eq("is_active", True)
            .eq("is_validated", True)
            .execute()
            .data
            or []
        )
        for row in rows:
            metadata = row.get("metadata") or {}
            if metadata.get("scope") == "session" and metadata.get("session_id") == session_id:
                return True
        return False

    def cleanup_session(self, session_id: str) -> int:
        rows = (
            self.supabase.table("noidung2")
            .select("sothutund, metadata")
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        ids = [
            row["sothutund"]
            for row in rows
            if isinstance(row.get("metadata"), dict)
            and row["metadata"].get("scope") == "session"
            and row["metadata"].get("session_id") == session_id
        ]
        return self._delete_ids(ids)

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        rows = (
            self.supabase.table("noidung2")
            .select("sothutund, metadata")
            .eq("is_active", True)
            .execute()
            .data
            or []
        )
        expired_ids: List[int] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            expires_at = str(metadata.get("expires_at") or "").strip()
            if metadata.get("scope") != "session" or not expires_at:
                continue
            try:
                if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= now:
                    expired_ids.append(int(row["sothutund"]))
            except ValueError:
                continue
        return self._delete_ids(expired_ids)

    def _update_file_active_state(self, *, file_id: str, is_active: bool) -> int:
        response = (
            self.supabase.table("noidung2")
            .update({"is_active": is_active, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("file_id", file_id)
            .execute()
        )
        return len(response.data or [])

    def _delete_ids(self, ids: List[int]) -> int:
        if not ids:
            return 0
        response = self.supabase.table("noidung2").delete().in_("sothutund", ids).execute()
        return len(response.data or [])

    def _build_search_text(
        self,
        *,
        title: str,
        so_hieu: Optional[str],
        section_path: str,
        content: str,
        rela: List[str],
    ) -> str:
        parts = [title, so_hieu or "", section_path, content, "; ".join(rela)]
        return "\n".join(part.strip() for part in parts if part and str(part).strip())

    def _guess_so_hieu(self, file_name: str) -> str:
        if match := re.search(r"(\d+/\d+/[A-ZĐ\-]+)", file_name, re.I):
            return match.group(1).upper()
        return ""

    def _guess_title(self, file_name: str) -> str:
        stem = os.path.splitext(file_name)[0]
        return stem.replace("_", " ").replace("-", " ").strip()

    def _guess_extension(self, file_name: str) -> str:
        return os.path.splitext(file_name)[1].lstrip(".").lower()
