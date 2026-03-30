import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI
from pydantic import ValidationError

from prompts.legal_extraction_prompts import LEGAL_EXTRACTION_SYSTEM_PROMPT, build_legal_extraction_user_prompt
from schema.legal_ingest_schema import ExtractedNode, ParsedNodeResult, ParsedSegment


logger = logging.getLogger("LEGAL_PARSER")

LEVEL_ORDER = {"CHUONG": 1, "MUC": 2, "DIEU": 3, "KHOAN": 4, "DIEM": 5, "DOAN": 6}


class LegalParserService:
    def __init__(self, api_key: str, model_name: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def segment_document(self, raw_text: str) -> List[ParsedSegment]:
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        segments: List[ParsedSegment] = []
        current: Optional[Dict[str, Any]] = None
        active_refs: Dict[str, str] = {}
        active_titles: Dict[str, str] = {}
        order = 0

        def trim_active(level_name: str) -> None:
            current_level = LEVEL_ORDER[level_name]
            for key in list(active_refs.keys()):
                if LEVEL_ORDER[key] >= current_level:
                    active_refs.pop(key, None)
                    active_titles.pop(key, None)

        def finalize_current() -> None:
            if not current:
                return
            segment_text = "\n".join(current["lines"]).strip()
            if not segment_text:
                return
            segments.append(
                ParsedSegment(
                    segment_ref=current["segment_ref"],
                    parent_ref=current["parent_ref"],
                    segment_text=segment_text,
                    detected_type=current["detected_type"],
                    ky_hieu_hint=current["ky_hieu_hint"],
                    thu_tu_hint=current["thu_tu_hint"],
                    hierarchy_title=current["hierarchy_title"],
                    parent_context=current["parent_context"],
                )
            )

        def build_parent_context(parent_ref: Optional[str]) -> Optional[str]:
            if not parent_ref:
                return None
            for level_name in ("DIEM", "KHOAN", "DIEU", "MUC", "CHUONG"):
                if active_refs.get(level_name) == parent_ref:
                    return active_titles.get(level_name)
            return None

        for raw_line in lines:
            detected = self._detect_structure(raw_line)
            if detected:
                finalize_current()
                order += 1
                detected_type, ky_hieu_hint, thu_tu_hint = detected
                trim_active(detected_type)
                parent_ref = self._resolve_parent_ref(detected_type, active_refs)
                segment_ref = f"SEG-{order}"
                current = {
                    "segment_ref": segment_ref,
                    "parent_ref": parent_ref,
                    "detected_type": detected_type,
                    "ky_hieu_hint": ky_hieu_hint,
                    "thu_tu_hint": thu_tu_hint,
                    "hierarchy_title": raw_line,
                    "parent_context": build_parent_context(parent_ref),
                    "lines": [raw_line],
                }
                active_refs[detected_type] = segment_ref
                active_titles[detected_type] = raw_line
                continue

            if current is None:
                order += 1
                parent_ref = self._deepest_parent_ref(active_refs)
                current = {
                    "segment_ref": f"SEG-{order}",
                    "parent_ref": parent_ref,
                    "detected_type": "DOAN",
                    "ky_hieu_hint": None,
                    "thu_tu_hint": None,
                    "hierarchy_title": raw_line[:100],
                    "parent_context": build_parent_context(parent_ref),
                    "lines": [raw_line],
                }
            else:
                current["lines"].append(raw_line)

        finalize_current()
        return segments

    def parse_segments(self, so_hieu: str, segments: List[ParsedSegment]) -> List[ParsedNodeResult]:
        results: List[ParsedNodeResult] = []
        for segment in segments:
            raw_json, validation_errors = self._extract_json(so_hieu, segment)
            normalized_node = None
            if not validation_errors:
                normalized_node, validation_errors = self._validate_json(raw_json, segment)
            results.append(
                ParsedNodeResult(
                    segment_ref=segment.segment_ref,
                    parent_ref=segment.parent_ref,
                    source_segment=segment,
                    extracted_json=raw_json,
                    normalized_node=normalized_node,
                    is_validated=not validation_errors and normalized_node is not None,
                    validation_errors=validation_errors,
                )
            )
        return results

    def _extract_json(self, so_hieu: str, segment: ParsedSegment) -> Tuple[Dict[str, Any], List[str]]:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": LEGAL_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": build_legal_extraction_user_prompt(so_hieu, segment)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            return self._load_json(content), []
        except Exception as exc:
            logger.exception("LLM extraction failed for %s", segment.segment_ref)
            return {"segment_ref": segment.segment_ref, "error": str(exc)}, [f"llm_extract_error: {exc}"]

    def _load_json(self, content: str) -> Dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        loaded = json.loads(cleaned)
        if not isinstance(loaded, dict):
            raise ValueError("LLM phai tra ve JSON object")
        return loaded

    def _validate_json(self, payload: Dict[str, Any], segment: ParsedSegment) -> Tuple[Optional[ExtractedNode], List[str]]:
        errors: List[str] = []
        candidate = dict(payload)
        candidate["parent_ref"] = payload.get("parent_ref") or segment.parent_ref
        candidate["loai_muc"] = self._coerce_node_type(payload.get("loai_muc"), segment.detected_type)
        candidate["ky_hieu"] = payload.get("ky_hieu") or segment.ky_hieu_hint
        candidate["thu_tu"] = self._coerce_int(payload.get("thu_tu"), segment.thu_tu_hint)
        candidate["rela"] = self._normalize_rela(payload.get("rela"))
        min_km, max_km = self._derive_km_range(payload.get("noidung") or segment.segment_text, payload.get("min_km"), payload.get("max_km"))
        candidate["min_km"] = min_km
        candidate["max_km"] = max_km
        candidate["confidence"] = self._coerce_confidence(payload.get("confidence"))

        try:
            node = ExtractedNode.parse_obj(candidate)
        except ValidationError as exc:
            errors.extend(err["msg"] for err in exc.errors())
            return None, errors
        return node, errors

    def _detect_structure(self, line: str) -> Optional[Tuple[str, Optional[str], Optional[int]]]:
        chapter_match = re.match(r"^(Chương\s+[IVXLCDM0-9A-Z]+)\b", line, re.IGNORECASE)
        if chapter_match:
            return "CHUONG", chapter_match.group(1).strip(), self._roman_to_int(chapter_match.group(1))

        section_match = re.match(r"^(Mục\s+\d+[A-Z]?)\b", line, re.IGNORECASE)
        if section_match:
            return "MUC", section_match.group(1).strip(), self._extract_first_int(section_match.group(1))

        article_match = re.match(r"^(Điều\s+(\d+[A-Z]?))\s*[\.\-]?", line, re.IGNORECASE)
        if article_match:
            return "DIEU", article_match.group(1).strip(), self._extract_first_int(article_match.group(2))

        clause_match = re.match(r"^(\d+)\.\s+", line)
        if clause_match:
            return "KHOAN", f"Khoản {clause_match.group(1)}", int(clause_match.group(1))

        point_match = re.match(r"^([a-zA-ZđĐ])\)\s+", line)
        if point_match:
            return "DIEM", f"Điểm {point_match.group(1).lower()}", self._letter_to_index(point_match.group(1))
        return None

    def _resolve_parent_ref(self, detected_type: str, active_refs: Dict[str, str]) -> Optional[str]:
        if detected_type == "CHUONG":
            return None
        if detected_type == "MUC":
            return active_refs.get("CHUONG")
        if detected_type == "DIEU":
            return active_refs.get("MUC") or active_refs.get("CHUONG")
        if detected_type == "KHOAN":
            return active_refs.get("DIEU")
        if detected_type == "DIEM":
            return active_refs.get("KHOAN")
        return self._deepest_parent_ref(active_refs)

    def _deepest_parent_ref(self, active_refs: Dict[str, str]) -> Optional[str]:
        for level_name in ("DIEM", "KHOAN", "DIEU", "MUC", "CHUONG"):
            if active_refs.get(level_name):
                return active_refs[level_name]
        return None

    def _coerce_node_type(self, value: Any, fallback: str) -> str:
        normalized = str(value or "").strip().upper()
        return normalized if normalized in {"CHUONG", "MUC", "DIEU", "KHOAN", "DIEM", "DOAN"} else fallback

    def _coerce_int(self, value: Any, fallback: Optional[int]) -> Optional[int]:
        if value is None or value == "":
            return fallback
        try:
            return int(str(value).strip())
        except ValueError:
            return fallback

    def _coerce_confidence(self, value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, numeric))

    def _normalize_rela(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]
        return []

    def _derive_km_range(self, text: str, raw_min: Any, raw_max: Any) -> Tuple[Optional[float], Optional[float]]:
        min_km = self._coerce_float(raw_min)
        max_km = self._coerce_float(raw_max)
        if min_km is not None or max_km is not None:
            return min_km, max_km

        normalized = text.replace(",", ".")
        between_match = re.search(r"từ\s+(\d+(?:\.\d+)?)\s*km(?:/h)?\s+(?:đến|-)\s+(\d+(?:\.\d+)?)\s*km", normalized, re.IGNORECASE)
        if between_match:
            return float(between_match.group(1)), float(between_match.group(2))

        above_match = re.search(r"từ\s+(\d+(?:\.\d+)?)\s*km(?:/h)?\s+trở lên", normalized, re.IGNORECASE)
        if above_match:
            return float(above_match.group(1)), None
        return None, None

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace(",", ".").strip())
        except ValueError:
            return None

    def _extract_first_int(self, value: str) -> Optional[int]:
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else None

    def _roman_to_int(self, value: str) -> Optional[int]:
        roman_match = re.search(r"\b([IVXLCDM]+)\b", value, re.IGNORECASE)
        if not roman_match:
            return self._extract_first_int(value)
        roman = roman_match.group(1).upper()
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

    def _letter_to_index(self, value: str) -> int:
        letter = value.lower()
        return ord(letter[0]) - 96 if letter and "a" <= letter[0] <= "z" else 1
