import io
import logging
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from typing import List
from xml.etree import ElementTree


logger = logging.getLogger("LEGAL_FILE_EXTRACT")

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


@dataclass
class ExtractedTextResult:
    raw_text: str
    source_file_type: str
    source_file_name: str


class UnsupportedFileTypeError(ValueError):
    pass


class FileTextExtractionError(ValueError):
    pass


class FileExtractService:
    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}
    NOISE_PATTERNS = [
        re.compile(pattern, re.I)
        for pattern in (
            r"^nguoi ky\b",
            r"^ky boi\b",
            r"^ky dien tu\b",
            r"^chu ky so\b",
            r"^thoi gian ky\b",
            r"^ngay ky\b",
            r"^serial number\b",
            r"^issued by\b",
            r"^valid from\b",
            r"^ma xac thuc\b",
            r"^email\b",
            r"^co quan ky\b",
            r"^thong tin ky so\b",
            r"^tai lieu duoc ky so\b",
            r"^van ban duoc ky so\b",
            r"^trich xuat tu he thong\b",
            r"^scan(ed)? by\b",
            r"^duoc tao boi\b",
            r"^pdf\b",
            r"^watermark\b",
            r"^https?://",
            r"^www\.",
        )
    ]

    def extract(self, file_name: str, content: bytes) -> ExtractedTextResult:
        extension = self._get_extension(file_name)
        if extension == ".pdf":
            raw_text = self._extract_pdf_text(content)
        elif extension == ".docx":
            raw_text = self._extract_docx_text(content)
        elif extension == ".txt":
            raw_text = self._extract_txt_text(content)
        else:
            raise UnsupportedFileTypeError("Chi ho tro file .pdf, .docx, .txt")

        cleaned_text = self._clean_text(raw_text)
        if not cleaned_text:
            raise FileTextExtractionError("Khong trich xuat duoc noi dung tu file upload")

        return ExtractedTextResult(
            raw_text=cleaned_text,
            source_file_type=extension.lstrip("."),
            source_file_name=file_name,
        )

    def _get_extension(self, file_name: str) -> str:
        lower_name = (file_name or "").lower()
        for extension in self.SUPPORTED_EXTENSIONS:
            if lower_name.endswith(extension):
                return extension
        raise UnsupportedFileTypeError("Chi ho tro file .pdf, .docx, .txt")

    def _extract_pdf_text(self, content: bytes) -> str:
        if PdfReader is None:
            raise FileTextExtractionError("Server chua cai pypdf de doc file PDF.")

        reader = PdfReader(io.BytesIO(content))
        pages: List[str] = []
        total_pages = len(reader.pages)
        extracted_pages = 0
        for page_index, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            if page_text:
                extracted_pages += 1
                pages.append(f"[PAGE {page_index}]\n{page_text}")

        logger.info(
            "pdf extraction | total_pages=%s | extracted_pages=%s",
            total_pages,
            extracted_pages,
        )

        if not pages:
            raise FileTextExtractionError(
                "PDF khong co text layer de trich xuat. Co the day la file scan/ky so dang anh, can OCR truoc khi ingest."
            )

        return "\n\n".join(pages)

    def _extract_docx_text(self, content: bytes) -> str:
        paragraphs: List[str] = []
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_content = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml_content)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for paragraph in root.findall(".//w:p", ns):
            text_nodes = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
            paragraph_text = "".join(text_nodes).strip()
            if paragraph_text:
                paragraphs.append(paragraph_text)
        return "\n".join(paragraphs)

    def _extract_txt_text(self, content: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "cp1258", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    def _clean_text(self, raw_text: str) -> str:
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\u00a0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        lines = self._remove_repeated_headers_footers(lines)
        lines = [line for line in lines if not self._is_noise_line(line)]
        normalized = "\n".join(lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _remove_repeated_headers_footers(self, lines: List[str]) -> List[str]:
        counts = Counter(line for line in lines if len(line) <= 120)
        removable = set()
        for line, count in counts.items():
            normalized = line.lower()
            looks_like_page = bool(re.search(r"^(trang|page)\s+\d+|\[page\s+\d+\]$", normalized))
            upper_ratio = sum(ch.isupper() for ch in line) / max(len(line), 1)
            if count >= 3 and (looks_like_page or upper_ratio >= 0.7):
                removable.add(line)
        filtered = [line for line in lines if line not in removable]
        if removable:
            logger.info("Da loai bo %s dong header/footer lap lai", len(removable))
        return filtered

    def _is_noise_line(self, line: str) -> bool:
        normalized = line.strip()
        if not normalized:
            return True
        if re.match(r"^\[PAGE\s+\d+\]$", normalized, re.I):
            return False
        lowered = normalized.lower()
        if any(pattern.search(lowered) for pattern in self.NOISE_PATTERNS):
            return True
        if "@" in normalized and "." in normalized:
            return True
        if re.match(r"^(trang|page)\s+\d+(?:/\d+)?$", lowered):
            return True
        if re.match(r"^\d+\s*/\s*\d+$", lowered):
            return True
        if re.match(r"^(?:-|_){4,}$", normalized):
            return True
        if re.match(r"^[A-Z0-9 .:/-]{8,}$", normalized):
            digit_ratio = sum(ch.isdigit() for ch in normalized) / max(len(normalized), 1)
            if digit_ratio >= 0.35 and ("pdf" in lowered or "ky" in lowered or "serial" in lowered):
                return True
        alpha_count = sum(ch.isalpha() for ch in normalized)
        if alpha_count == 0 and re.search(r"\d", normalized):
            return True
        return False
