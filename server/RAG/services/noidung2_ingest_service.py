import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from supabase import Client, create_client

from schema.legal_ingest_schema import IngestPreviewNode, LegalIngestResponse, LegalIngestSettings, ParsedNodeResult
from services.embedding_service import EmbeddingService
from services.file_extract_service import FileExtractService
from services.legal_parser_service import LegalParserService


logger = logging.getLogger("NOIDUNG2_INGEST")


class Noidung2IngestService:
    def __init__(self, settings: LegalIngestSettings) -> None:
        self.settings = settings
        self.file_extract_service = FileExtractService()
        self.legal_parser_service = LegalParserService(api_key=settings.openai_api_key, model_name=settings.extraction_model)
        self.embedding_service = EmbeddingService(settings)
        self.supabase: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    def ingest_document(self, file_name: str, file_bytes: bytes, so_hieu: str, modified_by: Optional[int]) -> LegalIngestResponse:
        logger.info("file received | name=%s | size=%s", file_name, len(file_bytes))
        extracted = self.file_extract_service.extract(file_name=file_name, content=file_bytes)
        logger.info("text extracted | chars=%s", len(extracted.raw_text))

        segments = self.legal_parser_service.segment_document(extracted.raw_text)
        logger.info("segments count | count=%s", len(segments))

        parsed_results = self.legal_parser_service.parse_segments(so_hieu=so_hieu, segments=segments)
        logger.info("llm parsed count | count=%s", len(parsed_results))

        validated_count = sum(1 for item in parsed_results if item.is_validated)
        logger.info("valid count | count=%s", validated_count)

        inserted_count = self._insert_nodes(
            results=parsed_results,
            extracted_raw_text=extracted.raw_text,
            source_file_name=extracted.source_file_name,
            source_file_type=extracted.source_file_type,
            so_hieu=so_hieu,
            modified_by=modified_by,
        )
        failed_count = len(parsed_results) - inserted_count
        logger.info("inserted count | inserted=%s", inserted_count)
        logger.info("failed count | failed=%s", failed_count)

        preview = [self._to_preview_node(item) for item in parsed_results[:5]]
        return LegalIngestResponse(
            success=inserted_count > 0,
            file_name=file_name,
            segments_count=len(segments),
            parsed_count=len(parsed_results),
            validated_count=validated_count,
            inserted_count=inserted_count,
            failed_count=failed_count,
            preview=preview,
        )

    def _insert_nodes(
        self,
        results: List[ParsedNodeResult],
        extracted_raw_text: str,
        source_file_name: str,
        source_file_type: str,
        so_hieu: str,
        modified_by: Optional[int],
    ) -> int:
        inserted_count = 0
        inserted_id_map: Dict[str, int] = {}
        parent_map = {item.segment_ref: item.parent_ref for item in results}

        for item in results:
            if not item.is_validated or not item.normalized_node:
                continue

            try:
                parent_id = self._resolve_parent_id(item.parent_ref, inserted_id_map, parent_map)
                rela_text = " ".join(item.normalized_node.rela)
                embedding_error = None
                try:
                    main_embedding = self.embedding_service.generate_embedding(item.normalized_node.noidung)
                    rela_embedding = self.embedding_service.generate_embedding(rela_text) if rela_text else None
                except Exception as exc:
                    logger.exception("embedding error | ref=%s", item.segment_ref)
                    main_embedding = None
                    rela_embedding = None
                    embedding_error = str(exc)

                payload = {
                    "noidung": item.normalized_node.noidung,
                    "sohieu": so_hieu,
                    "sothutund_cha": parent_id,
                    "search_text": self._build_search_text(item.normalized_node.noidung, item.normalized_node.ky_hieu, item.normalized_node.rela),
                    "modified_by": modified_by,
                    "modified_at": datetime.now(timezone.utc).isoformat(),
                    "embedding": self.embedding_service.to_pgvector(main_embedding),
                    "loai_muc": item.normalized_node.loai_muc,
                    "ky_hieu": item.normalized_node.ky_hieu,
                    "thu_tu": item.normalized_node.thu_tu,
                    "rela": item.normalized_node.rela or None,
                    "rela_embed": self.embedding_service.to_pgvector(rela_embedding),
                    "min_km": item.normalized_node.min_km,
                    "max_km": item.normalized_node.max_km,
                    "source_file_name": source_file_name,
                    "source_file_type": source_file_type,
                    "raw_text": extracted_raw_text,
                    "extracted_json": item.extracted_json,
                    "is_validated": True,
                    "validation_errors": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                response = self.supabase.table("noidung2").insert(payload).execute()
                inserted_row = response.data[0] if response.data else {}
                inserted_id = self._extract_inserted_id(inserted_row)
                item.inserted_id = inserted_id
                item.embedding_error = embedding_error
                if inserted_id is not None:
                    inserted_id_map[item.segment_ref] = inserted_id
                inserted_count += 1
            except Exception as exc:
                logger.exception("insert error | ref=%s", item.segment_ref)
                item.validation_errors.append(f"insert_error: {exc}")
        return inserted_count

    def _resolve_parent_id(self, parent_ref: Optional[str], inserted_id_map: Dict[str, int], parent_map: Dict[str, Optional[str]]) -> Optional[int]:
        cursor = parent_ref
        while cursor:
            if cursor in inserted_id_map:
                return inserted_id_map[cursor]
            cursor = parent_map.get(cursor)
        return None

    def _extract_inserted_id(self, row: Dict[str, object]) -> Optional[int]:
        for key in ("sothutund", "sothutundnd", "soThuTuND"):
            if key in row and row[key] is not None:
                return int(row[key])
        return None

    def _build_search_text(self, noidung: str, ky_hieu: Optional[str], rela: List[str]) -> str:
        parts = [noidung.strip()]
        if ky_hieu:
            parts.append(ky_hieu.strip())
        if rela:
            parts.extend(rela)
        return " ".join(part for part in parts if part).strip()

    def _to_preview_node(self, result: ParsedNodeResult) -> IngestPreviewNode:
        node = result.normalized_node
        return IngestPreviewNode(
            segment_ref=result.segment_ref,
            loai_muc=node.loai_muc if node else None,
            ky_hieu=node.ky_hieu if node else None,
            thu_tu=node.thu_tu if node else None,
            noidung=(node.noidung if node else result.source_segment.segment_text)[:500],
            parent_ref=result.parent_ref,
            inserted_id=result.inserted_id,
            is_validated=result.is_validated,
            validation_errors=result.validation_errors,
        )
