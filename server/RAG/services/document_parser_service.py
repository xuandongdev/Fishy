import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from services.file_extract_service import FileExtractService, FileTextExtractionError, UnsupportedFileTypeError


logger = logging.getLogger("DOCUMENT_PARSER_SERVICE")

PAGE_RE = re.compile(r"^\[PAGE\s+(\d+)\]$", re.I)
PHAN_RE = re.compile(r"^phan\s+([ivxlcdm0-9a-z]+)\b(?:[\s\.\-:]+.*)?$", re.I)
CHUONG_RE = re.compile(r"^chuong\s+([ivxlcdm0-9a-z]+)\b(?:[\s\.\-:]+.*)?$", re.I)
MUC_RE = re.compile(r"^muc\s+([0-9ivxlcdm]+[a-z]?)\b(?:[\s\.\-:]+.*)?$", re.I)
DIEU_RE = re.compile(r"^dieu\s+(\d+[a-z]?)\b(?:[\s\.\-:]+.*)?$", re.I)
KHOAN_RE = re.compile(r"^(?:khoan\s+(\d+[a-z]?)\b|(\d+[a-z]?)\.\s+)", re.I)
DIEM_RE = re.compile(r"^(?:diem\s+([a-zd])\b|([a-zd])\)\s+)", re.I)
NOISE_LINE_RE = re.compile(
    r"(nguoi ky|ky dien tu|chu ky so|email|watermark|serial number|issued by|valid from|scan|thoi gian ky)",
    re.I,
)
MEANINGFUL_NODE_TYPES = {"DIEU", "KHOAN", "DIEM", "DOAN"}


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

        nodes = self._build_legal_nodes(text)
        sections = self._build_sections_from_nodes(nodes)
        if not sections:
            raise ValueError("Khong nhan dien duoc cau truc phap ly hop le tu file upload.")

        logger.info(
            "document parsed | file=%s | sections=%s | nodes=%s | validated=%s",
            file_name,
            len(sections),
            len(nodes),
            sum(1 for node in nodes if node.get("is_validated")),
        )
        return {
            "text": text,
            "doc_type": result.source_file_type,
            "filename": result.source_file_name,
            "nodes": nodes,
            "sections": sections,
            "sections_count": len(sections),
            "chunking_mode": "legal_structure",
        }

    def _build_legal_nodes(self, text: str) -> List[Dict[str, Any]]:
        lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
        nodes: List[Dict[str, Any]] = []
        stack: Dict[str, str] = {}
        current_page = 1
        node_index = 0

        def next_ref() -> str:
            nonlocal node_index
            node_index += 1
            return f"NODE-{node_index}"

        def trim_stack(level_name: str) -> None:
            level_order = {"PHAN": 1, "CHUONG": 2, "MUC": 3, "DIEU": 4, "KHOAN": 5, "DIEM": 6, "DOAN": 7}
            current_level = level_order[level_name]
            for key in list(stack.keys()):
                if level_order[key] >= current_level:
                    stack.pop(key, None)

        def deepest_ref() -> Optional[str]:
            for key in ("DIEM", "KHOAN", "DIEU", "MUC", "CHUONG", "PHAN"):
                if stack.get(key):
                    return stack[key]
            return None

        def resolve_parent(node_type: str) -> Optional[str]:
            if node_type == "PHAN":
                return None
            if node_type == "CHUONG":
                return stack.get("PHAN")
            if node_type == "MUC":
                return stack.get("CHUONG") or stack.get("PHAN")
            if node_type == "DIEU":
                return stack.get("MUC") or stack.get("CHUONG") or stack.get("PHAN")
            if node_type == "KHOAN":
                return stack.get("DIEU")
            if node_type == "DIEM":
                return stack.get("KHOAN") or stack.get("DIEU")
            return deepest_ref()

        def append_to_current(line: str) -> None:
            target = self._find_append_target(nodes, stack)
            if target is None:
                doan_ref = next_ref()
                parent_ref = deepest_ref()
                nodes.append(
                    self._create_node(
                        node_ref=doan_ref,
                        parent_ref=parent_ref,
                        node_type="DOAN",
                        content=line,
                        page=current_page,
                        ky_hieu=None,
                        thu_tu=None,
                    )
                )
                stack["DOAN"] = doan_ref
                return

            target["noidung"] = f"{target['noidung']}\n{line}".strip()
            target["raw_text"] = f"{target['raw_text']}\n{line}".strip()
            target["page_end"] = current_page

        for raw_line in lines:
            if not raw_line:
                continue
            page_match = PAGE_RE.match(raw_line)
            if page_match:
                current_page = int(page_match.group(1))
                continue
            if self._is_noise_line(raw_line):
                continue

            detected = self._detect_structure(raw_line)
            if detected is None:
                append_to_current(raw_line)
                continue

            node_type, ky_hieu, thu_tu = detected
            trim_stack(node_type)
            parent_ref = resolve_parent(node_type)
            node_ref = next_ref()
            node = self._create_node(
                node_ref=node_ref,
                parent_ref=parent_ref,
                node_type=node_type,
                content=raw_line,
                page=current_page,
                ky_hieu=ky_hieu,
                thu_tu=thu_tu,
            )
            nodes.append(node)
            stack[node_type] = node_ref

        self._finalize_nodes(nodes)
        return nodes

    def _build_sections_from_nodes(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        for node in nodes:
            if not node.get("is_validated"):
                continue
            sections.append(
                {
                    "section_path": node.get("section_path") or node.get("ky_hieu") or node.get("loai_muc"),
                    "heading": node.get("ky_hieu") or node.get("loai_muc"),
                    "page_start": node.get("page_start"),
                    "page_end": node.get("page_end"),
                    "content": node.get("noidung") or "",
                    "chapter": node.get("chapter"),
                    "muc": node.get("muc"),
                    "dieu": node.get("dieu"),
                    "khoan": node.get("khoan"),
                    "diem": node.get("diem"),
                    "start_anchor": node.get("ky_hieu"),
                    "end_anchor": node.get("ky_hieu"),
                    "anchor_type": str(node.get("loai_muc") or "").lower(),
                }
            )
        return sections

    def _create_node(
        self,
        *,
        node_ref: str,
        parent_ref: Optional[str],
        node_type: str,
        content: str,
        page: int,
        ky_hieu: Optional[str],
        thu_tu: Optional[int],
    ) -> Dict[str, Any]:
        return {
            "node_ref": node_ref,
            "parent_ref": parent_ref,
            "loai_muc": node_type,
            "ky_hieu": ky_hieu,
            "thu_tu": thu_tu,
            "noidung": content.strip(),
            "raw_text": content.strip(),
            "page_start": page,
            "page_end": page,
            "rela": [],
            "min_km": None,
            "max_km": None,
            "section_path": None,
            "is_validated": False,
            "validation_errors": [],
            "chapter": None,
            "muc": None,
            "dieu": None,
            "khoan": None,
            "diem": None,
        }

    def _find_append_target(self, nodes: List[Dict[str, Any]], stack: Dict[str, str]) -> Optional[Dict[str, Any]]:
        ref_to_node = {node["node_ref"]: node for node in nodes}
        for key in ("DIEM", "KHOAN", "DIEU", "DOAN"):
            node_ref = stack.get(key)
            if node_ref and node_ref in ref_to_node:
                return ref_to_node[node_ref]
        return None

    def _detect_structure(self, line: str) -> Optional[Tuple[str, Optional[str], Optional[int]]]:
        normalized = self._normalize_ascii(line)

        if match := PHAN_RE.match(normalized):
            token = match.group(1)
            return "PHAN", f"PHAN {token.upper()}", self._coerce_order(token)
        if match := CHUONG_RE.match(normalized):
            token = match.group(1)
            return "CHUONG", f"CHUONG {token.upper()}", self._coerce_order(token)
        if match := MUC_RE.match(normalized):
            token = match.group(1)
            return "MUC", f"MUC {token.upper()}", self._coerce_order(token)
        if match := DIEU_RE.match(normalized):
            token = match.group(1)
            return "DIEU", f"DIEU {token.upper()}", self._coerce_order(token)
        if match := KHOAN_RE.match(normalized):
            token = match.group(1) or match.group(2)
            return "KHOAN", f"KHOAN {token}", self._coerce_order(token)
        if match := DIEM_RE.match(normalized):
            token = (match.group(1) or match.group(2) or "").lower()
            return "DIEM", f"DIEM {token}", self._letter_to_index(token)
        return None

    def _finalize_nodes(self, nodes: List[Dict[str, Any]]) -> None:
        ref_to_node = {node["node_ref"]: node for node in nodes}
        for node in nodes:
            lineage = self._build_lineage(node, ref_to_node)
            node["section_path"] = " > ".join(
                item.get("ky_hieu") or item.get("loai_muc") or ""
                for item in lineage
                if item.get("ky_hieu") or item.get("loai_muc")
            )
            node["chapter"] = self._find_lineage_unit(lineage, "CHUONG")
            node["muc"] = self._find_lineage_unit(lineage, "MUC")
            node["dieu"] = self._find_lineage_unit(lineage, "DIEU")
            node["khoan"] = self._find_lineage_unit(lineage, "KHOAN")
            node["diem"] = self._find_lineage_unit(lineage, "DIEM")
            node["min_km"], node["max_km"] = self._derive_km_range(node.get("noidung") or "")
            errors = self._validate_node(node)
            node["validation_errors"] = errors
            node["is_validated"] = not errors

    def _build_lineage(self, node: Dict[str, Any], ref_to_node: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        lineage: List[Dict[str, Any]] = []
        cursor: Optional[Dict[str, Any]] = node
        visited = set()
        while cursor is not None:
            node_ref = str(cursor.get("node_ref") or "")
            if not node_ref or node_ref in visited:
                break
            visited.add(node_ref)
            lineage.append(cursor)
            parent_ref = cursor.get("parent_ref")
            cursor = ref_to_node.get(str(parent_ref)) if parent_ref else None
        lineage.reverse()
        return lineage

    def _find_lineage_unit(self, lineage: List[Dict[str, Any]], target_type: str) -> Optional[str]:
        for item in reversed(lineage):
            if str(item.get("loai_muc") or "").upper() == target_type:
                return item.get("ky_hieu")
        return None

    def _validate_node(self, node: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        content = str(node.get("noidung") or "").strip()
        node_type = str(node.get("loai_muc") or "").upper()
        if not content:
            errors.append("missing_content")
            return errors
        if NOISE_LINE_RE.search(content):
            errors.append("noise_detected")
        if node_type not in MEANINGFUL_NODE_TYPES:
            errors.append("structural_only")
        normalized = self._normalize_ascii(content)
        token_count = len([token for token in normalized.split() if token])
        if node_type in MEANINGFUL_NODE_TYPES and token_count < 4:
            errors.append("content_too_short")
        return errors

    def _derive_km_range(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        normalized = self._normalize_ascii(text).replace(",", ".")
        if match := re.search(r"tu\s+(\d+(?:\.\d+)?)\s*km(?:/h)?\s+(?:den|-)\s+(\d+(?:\.\d+)?)\s*km", normalized):
            return float(match.group(1)), float(match.group(2))
        if match := re.search(r"tu\s+(\d+(?:\.\d+)?)\s*km(?:/h)?\s+tro\s+len", normalized):
            return float(match.group(1)), None
        return None, None

    def _is_noise_line(self, line: str) -> bool:
        if PAGE_RE.match(line):
            return False
        normalized = self._normalize_ascii(line)
        if not normalized:
            return True
        if NOISE_LINE_RE.search(normalized):
            return True
        if re.match(r"^(trang|page)\s+\d+(?:/\d+)?$", normalized):
            return True
        if re.match(r"^\d+\s*/\s*\d+$", normalized):
            return True
        return False

    def _coerce_order(self, token: Optional[str]) -> Optional[int]:
        if not token:
            return None
        if re.fullmatch(r"\d+", token):
            return int(token)
        roman = token.upper()
        if re.fullmatch(r"[IVXLCDM]+", roman):
            mapping = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
            total = 0
            previous = 0
            for char in reversed(roman):
                current = mapping[char]
                if current < previous:
                    total -= current
                else:
                    total += current
                    previous = current
            return total
        if match := re.search(r"\d+", token):
            return int(match.group(0))
        return None

    def _letter_to_index(self, token: str) -> Optional[int]:
        if not token:
            return None
        letter = token[0].lower()
        if "a" <= letter <= "z":
            return ord(letter) - 96
        return None

    def _normalize_ascii(self, text: str) -> str:
        normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.replace("đ", "d")
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()
