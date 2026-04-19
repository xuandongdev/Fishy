import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from services.file_extract_service import FileExtractService, FileTextExtractionError, UnsupportedFileTypeError


logger = logging.getLogger("DOCUMENT_PARSER_SERVICE")
PAGE_RE = re.compile(r"^\[PAGE\s+(\d+)\]$", re.I)
CHAPTER_RE = re.compile(r"^chuong\s+[ivxlcdm0-9]+(?:[\s\.\-:]+.*)?$", re.I)
MUC_RE = re.compile(r"^muc\s+[0-9ivxlcdm]+(?:[\s\.\-:]+.*)?$", re.I)
DIEU_RE = re.compile(r"^dieu\s+\d+[a-z]?(?:[\s\.\-:]+.*)?$", re.I)
GENERIC_HEADING_RE = re.compile(r"^[A-Z0-9][A-Z0-9\s\-\.:/]{6,120}$")


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
        lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
        legal_sections = self._build_legal_sections(lines)
        if legal_sections:
            logger.info(
                "document sections built | chunking_mode=%s | sections_count=%s",
                "legal_structure",
                len(legal_sections),
            )
            return {
                "sections": legal_sections,
                "sections_count": len(legal_sections),
                "chunking_mode": "legal_structure",
            }

        generic_sections = self._build_generic_sections(lines, text)
        logger.info(
            "document sections built | chunking_mode=%s | sections_count=%s",
            generic_sections["chunking_mode"],
            generic_sections["sections_count"],
        )
        return generic_sections

    def _build_legal_sections(self, lines: List[str]) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        current_page = 1
        chapter: Optional[str] = None
        muc: Optional[str] = None
        article_heading: Optional[str] = None
        article_lines: List[str] = []
        section_start_page = 1
        article_seen = False

        def flush_article(page_end: Optional[int] = None) -> None:
            nonlocal article_heading, article_lines, section_start_page, article_seen
            if not article_heading:
                article_lines = []
                return
            content = "\n".join(item for item in article_lines if item).strip()
            if len(content) < 20:
                article_lines = []
                article_heading = None
                return
            path_parts = [part for part in [chapter, muc, article_heading] if part]
            sections.append(
                {
                    "section_path": " > ".join(path_parts) if path_parts else article_heading,
                    "heading": article_heading,
                    "page_start": section_start_page,
                    "page_end": page_end if page_end is not None else current_page,
                    "content": content,
                    "chapter": chapter,
                    "muc": muc,
                    "dieu": self._extract_article_number(article_heading),
                    "khoan": None,
                    "diem": None,
                    "start_anchor": article_heading,
                    "end_anchor": article_heading,
                    "anchor_type": "dieu",
                }
            )
            article_lines = []
            article_heading = None
            article_seen = True

        for raw_line in lines:
            if not raw_line:
                continue
            page_match = PAGE_RE.match(raw_line)
            if page_match:
                current_page = int(page_match.group(1))
                continue

            ascii_line = self._normalize_ascii(raw_line)
            if CHAPTER_RE.match(ascii_line):
                flush_article(page_end=current_page)
                chapter = raw_line
                muc = None
                continue
            if MUC_RE.match(ascii_line):
                flush_article(page_end=current_page)
                muc = raw_line
                continue
            if DIEU_RE.match(ascii_line):
                flush_article(page_end=current_page)
                article_heading = raw_line
                article_lines = [raw_line]
                section_start_page = current_page
                continue
            if article_heading:
                article_lines.append(raw_line)

        flush_article(page_end=current_page)
        return sections if article_seen else []

    def _build_generic_sections(self, lines: List[str], full_text: str) -> Dict[str, Any]:
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
            normalized = full_text.strip()
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

        return {
            "sections": sections,
            "sections_count": len(sections),
            "chunking_mode": chunking_mode,
        }

    def _looks_like_heading(self, line: str) -> bool:
        normalized = line.strip()
        if len(normalized) < 3 or len(normalized) > 180:
            return False
        ascii_line = self._normalize_ascii(normalized)
        if CHAPTER_RE.match(ascii_line) or MUC_RE.match(ascii_line) or DIEU_RE.match(ascii_line):
            return True
        if re.match(r"^\d+(?:\.\d+){0,4}\.?\s+\S+", ascii_line):
            return True
        if GENERIC_HEADING_RE.match(normalized):
            return True
        alpha_chars = [ch for ch in normalized if ch.isalpha()]
        if alpha_chars:
            upper_ratio = sum(ch.isupper() for ch in alpha_chars) / len(alpha_chars)
            if upper_ratio >= 0.8 and len(normalized.split()) <= 14:
                return True
        return False

    def _update_section_path(self, current_path: List[str], heading: str) -> List[str]:
        heading_clean = heading.strip()
        lowered = self._normalize_ascii(heading_clean)
        if lowered.startswith("chuong"):
            return [heading_clean]
        if lowered.startswith("muc"):
            base = current_path[:1] if current_path else []
            return base + [heading_clean]
        if lowered.startswith("dieu"):
            base = current_path[:2] if len(current_path) >= 2 else current_path[:1]
            return base + [heading_clean]
        if re.match(r"^\d+(?:\.\d+)+", lowered):
            return current_path[:2] + [heading_clean]
        return current_path[:2] + [heading_clean] if current_path else [heading_clean]

    def _extract_article_number(self, heading: str) -> Optional[str]:
        match = re.match(r"^dieu\s+(\d+[a-z]?)", self._normalize_ascii(heading), re.I)
        return match.group(1) if match else None

    def _normalize_ascii(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return normalized.replace("đ", "d")
