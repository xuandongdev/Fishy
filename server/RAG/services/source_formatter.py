import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional


_WHITESPACE_RE = re.compile(r"\s+")
_DIEM_RE = re.compile(r"(?:^|[\s,;:])(?:diem\s+)?([a-zd])(?:\)|\b)", re.I)
_KHOAN_RE = re.compile(r"(?:^|[\s,;:])khoan\s+(\d+[a-z]?)\b", re.I)
_DIEU_RE = re.compile(r"(?:^|[\s,;:])dieu\s+(\d+[a-z]?)\b", re.I)
_CHUONG_RE = re.compile(r"(?:^|[\s,;:])chuong\s+([ivxlcdm0-9]+)\b", re.I)
_INTERNAL_LABELS = {
    "legal_db",
    "admin_upload",
    "session_docs",
    "user_upload",
    "source_type",
}


def format_legal_source(
    *,
    diem: Optional[str] = None,
    khoan: Optional[str] = None,
    dieu: Optional[str] = None,
    chapter: Optional[str] = None,
    ten_van_ban: Optional[str] = None,
    so_hieu: Optional[str] = None,
    prefix: str = "Nguồn: ",
) -> str:
    parts: List[str] = []
    normalized_diem = normalize_legal_unit("diem", diem)
    normalized_khoan = normalize_legal_unit("khoan", khoan)
    normalized_dieu = normalize_legal_unit("dieu", dieu)
    normalized_chapter = normalize_legal_unit("chuong", chapter)
    normalized_title = normalize_document_title(ten_van_ban)
    normalized_so_hieu = normalize_document_code(so_hieu)

    if normalized_diem:
        parts.append(normalized_diem)
    if normalized_khoan:
        parts.append(normalized_khoan)
    if normalized_dieu:
        parts.append(normalized_dieu)
    if normalized_chapter:
        parts.append(normalized_chapter)
    if normalized_title:
        if normalized_so_hieu:
            parts.append(f"{normalized_title} ({normalized_so_hieu})")
        else:
            parts.append(normalized_title)
    elif normalized_so_hieu:
        parts.append(f"({normalized_so_hieu})")

    body = ", ".join(part for part in parts if part).strip()
    if not body:
        return (prefix or "").strip() or "Nguồn:"
    return f"{prefix}{body}" if prefix else body


def format_uploaded_source(payload: Dict[str, Any]) -> str:
    return format_legal_source(
        diem=payload.get("diem"),
        khoan=payload.get("khoan"),
        dieu=payload.get("dieu"),
        chapter=payload.get("chapter"),
        ten_van_ban=payload.get("ten_van_ban") or payload.get("title") or payload.get("filename"),
        so_hieu=payload.get("so_hieu"),
    )


def format_db_source(row: Dict[str, Any], ancestors: Optional[Iterable[Dict[str, Any]]] = None) -> str:
    lineage = list(ancestors or [])
    lineage.append(row)

    diem = _pick_from_lineage(lineage, {"DIEM"}, "diem")
    khoan = _pick_from_lineage(lineage, {"KHOAN"}, "khoan")
    dieu = _pick_from_lineage(lineage, {"DIEU"}, "dieu")
    chapter = _pick_from_lineage(lineage, {"CHUONG"}, "chuong")

    if not any([diem, khoan, dieu, chapter]):
        parsed = parse_legal_path(str(row.get("duong_dan_phan_cap") or ""))
        diem = diem or parsed.get("diem")
        khoan = khoan or parsed.get("khoan")
        dieu = dieu or parsed.get("dieu")
        chapter = chapter or parsed.get("chapter")

    return format_legal_source(
        diem=diem,
        khoan=khoan,
        dieu=dieu,
        chapter=chapter,
        so_hieu=row.get("so_hieu") or row.get("sohieu"),
    )


def format_user_facing_source(item: Dict[str, Any]) -> str:
    source_type = str(item.get("source_type") or "").strip().lower()
    if source_type == "admin_upload":
        return format_uploaded_source(item)
    if source_type == "user_upload":
        return format_uploaded_source(item)
    if source_type == "legal_db":
        return format_db_source(item, ancestors=item.get("ancestor_nodes") or [])

    legal_label = format_legal_source(
        diem=item.get("diem"),
        khoan=item.get("khoan"),
        dieu=item.get("dieu"),
        chapter=item.get("chapter"),
        ten_van_ban=item.get("ten_van_ban") or item.get("title"),
        so_hieu=item.get("so_hieu") or item.get("sohieu"),
    )
    if legal_label != "Nguồn:":
        return legal_label

    title = normalize_document_title(item.get("ten_van_ban") or item.get("title"))
    so_hieu = normalize_document_code(item.get("so_hieu") or item.get("sohieu"))
    if title:
        return f"Nguồn: {title} ({so_hieu})" if so_hieu else f"Nguồn: {title}"

    filename = _normalize_spaces(item.get("filename"))
    if filename:
        return f"Nguồn: {filename}"

    url = _normalize_spaces(item.get("url"))
    if url:
        return f"Nguồn: {url}"

    label = _normalize_spaces(item.get("label"))
    if label and _normalize_ascii(label) not in _INTERNAL_LABELS:
        return f"Nguồn: {label}"

    return "Nguồn: Tài liệu tham chiếu"


def parse_legal_path(path: str) -> Dict[str, Optional[str]]:
    normalized = _normalize_ascii(path)
    diem_match = _DIEM_RE.search(normalized)
    khoan_match = _KHOAN_RE.search(normalized)
    dieu_match = _DIEU_RE.search(normalized)
    chapter_match = _CHUONG_RE.search(normalized)
    return {
        "diem": diem_match.group(1) if diem_match else None,
        "khoan": khoan_match.group(1) if khoan_match else None,
        "dieu": dieu_match.group(1) if dieu_match else None,
        "chapter": chapter_match.group(1).upper() if chapter_match else None,
    }


def normalize_legal_unit(unit_type: str, value: Optional[str]) -> Optional[str]:
    raw = _normalize_spaces(value)
    if not raw:
        return None
    normalized = _normalize_ascii(raw)
    if unit_type == "diem":
        match = _DIEM_RE.search(normalized)
        if not match:
            token = normalized.strip(" )(")
            match = re.match(r"^([a-zd])$", token, re.I)
        return f"Điểm {match.group(1).lower()}" if match else None
    if unit_type == "khoan":
        match = _KHOAN_RE.search(normalized) or re.match(r"^(\d+[a-z]?)$", normalized)
        return f"Khoản {match.group(1)}" if match else None
    if unit_type == "dieu":
        match = _DIEU_RE.search(normalized) or re.match(r"^(\d+[a-z]?)$", normalized)
        return f"Điều {match.group(1)}" if match else None
    if unit_type == "chuong":
        match = _CHUONG_RE.search(normalized) or re.match(r"^([ivxlcdm0-9]+)$", normalized, re.I)
        return f"Chương {match.group(1).upper()}" if match else None
    return raw


def normalize_document_title(value: Optional[str]) -> Optional[str]:
    raw = _normalize_spaces(value)
    if not raw:
        return None
    return raw.upper()


def normalize_document_code(value: Optional[str]) -> Optional[str]:
    raw = _normalize_spaces(value)
    return raw.upper() if raw else None


def _pick_from_lineage(lineage: List[Dict[str, Any]], accepted_types: set[str], unit_type: str) -> Optional[str]:
    for node in lineage:
        node_type = _normalize_ascii(str(node.get("loai_muc") or "")).upper()
        if node_type and node_type in accepted_types:
            normalized = normalize_legal_unit(unit_type, node.get("ky_hieu"))
            if normalized:
                return normalized.split(" ", 1)[1]
    return None


def _normalize_spaces(value: Optional[str]) -> Optional[str]:
    text = _WHITESPACE_RE.sub(" ", str(value or "").strip())
    return text or None


def _normalize_ascii(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("đ", "d")
    return _WHITESPACE_RE.sub(" ", normalized)
