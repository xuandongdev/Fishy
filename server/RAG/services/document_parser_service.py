import logging
import re
from typing import Any, Dict, List, Optional

from services.file_extract_service import FileExtractService, FileTextExtractionError, UnsupportedFileTypeError


logger = logging.getLogger("DOCUMENT_PARSER_SERVICE")
PAGE_RE = re.compile(r"^\[PAGE\s+(\d+)\]$", re.I)
HEADING_PATTERNS = [
    re.compile(r"^(chuong|chương)\s+[ivxlcdm0-9]+", re.I),
    re.compile(r"^(muc|mục)\s+[0-9ivxlcdm]+", re.I),
    re.compile(r"^(dieu|điều)\s+\d+", re.I),
    re.compile(r"^\d+(?:\.\d+){0,4}\.?\s+\S+"),
    re.compile(r"^[A-Z0-9][A-Z0-9\s\-\.:/]{6,120}$"),
]


class DocumentParserService:
    def __init__(self) -> None:
        self.file_extract_service = FileExtractService()

    def parse_document(self, file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        try:
            result = self.file_extract_service.extract(file_name, file_bytes)
        except (UnsupportedFileTypeError, FileTextExtractionError) as exc:
            logger.warning("document parse failed | file=%s | reason=%s", file_name, exc)
            raise ValueError(str(exc)) from exc
        except Exception as exc:
            logger.warning("document parse unexpected error | file=%s | reason=%s", file_name, exc)
            raise ValueError("Khong the doc noi dung tu file upload.") from exc

        text = (result.raw_text or "").strip()
        if len(text) < 40:
            raise ValueError("Noi dung trich xuat qua ngan de lap chi muc.")

        structured = self._build_sections(text)
        return {
            "text": text,
            "doc_type": result.source_file_type,
            "filename": result.source_file_name,
            "sections": structured["sections"],
            "sections_count": structured["sections_count"],
            "chunking_mode": structured["chunking_mode"],
        }

    def _build_sections(self, text: str) -> Dict[str, Any]:
        lines = [line.strip() for line in text.splitlines()]
        sections: List[Dict[str, Any]] = []
        buffer: List[str] = []
        current_heading = "Mo dau"
        current_page = 1
        section_start_page = 1
        current_path: List[str] = [current_heading]
        heading_count = 0

        def flush_section(page_end: Optional[int] = None) -> None:
            content = "\n".join(item for item in buffer if item).strip()
            if len(content) < 40:
                return
            sections.append(
                {
                    "section_path": " > ".join(current_path),
                    "heading": current_heading,
                    "page_start": section_start_page,
                    "page_end": page_end if page_end is not None else current_page,
                    "content": content,
                }
            )

        for raw_line in lines:
            if not raw_line:
                continue
            page_match = PAGE_RE.match(raw_line)
            if page_match:
                current_page = int(page_match.group(1))
                continue
            if self._looks_like_heading(raw_line):
                if buffer:
                    flush_section(page_end=current_page)
                    buffer = []
                current_heading = raw_line
                section_start_page = current_page
                current_path = self._update_section_path(current_path, raw_line)
                heading_count += 1
                continue
            buffer.append(raw_line)

        if buffer:
            flush_section(page_end=current_page)

        if not sections:
            normalized = text.strip()
            sections = [
                {
                    "section_path": "Toan van",
                    "heading": "Toan van",
                    "page_start": 1,
                    "page_end": current_page,
                    "content": normalized,
                }
            ]
            chunking_mode = "flat_fallback"
        else:
            chunking_mode = "heading_first" if heading_count > 0 else "flat_fallback"

        logger.info(
            "document sections built | chunking_mode=%s | sections_count=%s",
            chunking_mode,
            len(sections),
        )
        return {
            "sections": sections,
            "sections_count": len(sections),
            "chunking_mode": chunking_mode,
        }

    def _looks_like_heading(self, line: str) -> bool:
        normalized = line.strip()
        if len(normalized) < 3 or len(normalized) > 180:
            return False
        if any(pattern.match(normalized) for pattern in HEADING_PATTERNS):
            return True
        alpha_chars = [ch for ch in normalized if ch.isalpha()]
        if alpha_chars:
            upper_ratio = sum(ch.isupper() for ch in alpha_chars) / len(alpha_chars)
            if upper_ratio >= 0.8 and len(normalized.split()) <= 14:
                return True
        return False

    def _update_section_path(self, current_path: List[str], heading: str) -> List[str]:
        heading_clean = heading.strip()
        lowered = heading_clean.lower()
        if lowered.startswith(("chuong", "chương")):
            return [heading_clean]
        if lowered.startswith(("muc", "mục")):
            base = current_path[:1] if current_path else []
            return base + [heading_clean]
        if lowered.startswith(("dieu", "điều")):
            base = current_path[:2] if len(current_path) >= 2 else current_path[:1]
            return base + [heading_clean]
        if re.match(r"^\d+(?:\.\d+)+", heading_clean):
            return current_path[:2] + [heading_clean]
        return current_path[:2] + [heading_clean] if current_path else [heading_clean]
