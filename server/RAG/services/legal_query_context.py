import re
import unicodedata
from typing import Dict, List, Optional

VEHICLE_TYPES = {"o_to", "xe_may", "xe_dap", "di_bo", "khac"}

VEHICLE_TYPE_TO_PHRASE = {
    "xe_may": "xe máy",
    "o_to": "ô tô",
    "xe_dap": "xe đạp",
    "di_bo": "người đi bộ",
}

FOLLOWUP_PREFIXES = (
    "vậy còn",
    "vay con",
    "thế còn",
    "the con",
    "thế nếu",
    "the neu",
    "nếu vậy",
    "neu vay",
    "còn",
    "con",
    "nếu",
    "neu",
    "trường hợp đó",
    "truong hop do",
    "trường hợp này",
    "truong hop nay",
    "trường hợp ấy",
    "truong hop ay",
    "thế sao",
    "the sao",
    "thì sao",
    "thi sao",
    "vậy",
    "vay",
)

SPEED_KEYWORDS = (
    "quá tốc độ",
    "qua toc do",
    "vượt tốc độ",
    "vuot toc do",
    "chạy quá",
    "chay qua",
    "tốc độ",
    "toc do",
    "km/h",
    "km",
    "cây",
)

ACTION_PATTERNS = {
    "vuot_den_do": [
        r"vượt đèn đỏ",
        r"vuot den do",
        r"không chấp hành hiệu lệnh đèn tín hiệu",
        r"khong chap hanh hieu lenh den tin hieu",
        r"đèn đỏ",
        r"den do",
    ],
    "qua_toc_do": [
        r"quá tốc độ",
        r"qua toc do",
        r"vượt tốc độ",
        r"vuot toc do",
        r"chạy quá",
        r"chay qua",
        r"tốc độ",
        r"toc do",
        r"km/h",
        r"km",
        r"cây",
    ],
    "nong_do_con": [
        r"nồng độ cồn",
        r"nong do con",
        r"cồn",
        r"bia rượu",
        r"bia ruou",
    ],
    "khong_doi_mu": [
        r"không đội mũ",
        r"khong doi mu",
        r"không đội mũ bảo hiểm",
        r"khong doi mu bao hiem",
        r"mũ bảo hiểm",
        r"mu bao hiem",
    ],
    "cho_qua_nguoi": [
        r"chở quá",
        r"cho qua",
        r"quá số người",
        r"qua so nguoi",
        r"chở ba",
        r"cho ba",
        r"chở bốn",
        r"cho bon",
    ],
    "di_sai_lan": [
        r"sai làn",
        r"sai lan",
        r"không đúng làn",
        r"khong dung lan",
        r"phần đường",
        r"phan duong",
    ],
}


def normalize_legal_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def detect_vehicle_type(query: str) -> str:
    q = normalize_legal_text(query)
    if re.search(
        r"\b(o to|oto|xe hoi|xe con|xe tai|xe khach|xe ban tai|dau keo|container|ro mooc|so mi ro mooc)\b",
        q,
    ):
        return "o_to"
    if re.search(r"\b(xe may|mo to|moto|motor|xe gan may)\b", q):
        return "xe_may"
    if re.search(r"\b(xe dap|xe dap dien|xe tho so)\b", q):
        return "xe_dap"
    if re.search(r"\b(di bo|nguoi di bo|bo hanh)\b", q):
        return "di_bo"
    return "khac"


_KM_PATTERNS = [
    re.compile(r"(?:quá|qua|vượt|vuot|chạy|chay)?\s*(?:tốc độ|toc do)?\s*(\d+(?:[\.,]\d+)?)\s*(?:km/h|kmh|km|cây)\b"),
    re.compile(r"(?:quá|qua|vượt|vuot)\s*(\d+(?:[\.,]\d+)?)\b"),
]


def extract_km(query: str) -> Optional[float]:
    q = normalize_legal_text(query)
    for pattern in _KM_PATTERNS:
        match = pattern.search(q)
        if not match:
            continue
        raw = match.group(1).replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def detect_legal_action(query: str) -> Optional[str]:
    q = normalize_legal_text(query)
    for action, patterns in ACTION_PATTERNS.items():
        if any(re.search(pattern, q) for pattern in patterns):
            return action
    return None


def is_followup_question(query: str) -> bool:
    q = normalize_legal_text(query)
    if not q:
        return False
    if any(q.startswith(prefix) for prefix in FOLLOWUP_PREFIXES):
        return True
    token_count = len(q.split())
    if token_count <= 6 and (extract_km(q) is not None or detect_vehicle_type(q) != "khac"):
        return True
    if token_count <= 8 and detect_legal_action(q) is None:
        return True
    return False


def infer_vehicle_from_history(history: List[Dict[str, str]]) -> str:
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        detected = detect_vehicle_type(item.get("content") or "")
        if detected != "khac":
            return detected
    return "khac"


def infer_action_from_history(history: List[Dict[str, str]]) -> Optional[str]:
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        action = detect_legal_action(item.get("content") or "")
        if action:
            return action
    return None


def _vehicle_phrase(vehicle_type: str) -> Optional[str]:
    return VEHICLE_TYPE_TO_PHRASE.get(vehicle_type)


def _action_phrase(action: Optional[str], question: str, km_value: Optional[float]) -> Optional[str]:
    normalized = normalize_legal_text(question)
    if action == "vuot_den_do":
        return "vượt đèn đỏ"
    if action == "nong_do_con":
        return "vi phạm nồng độ cồn"
    if action == "khong_doi_mu":
        return "không đội mũ bảo hiểm"
    if action == "cho_qua_nguoi":
        if match := re.search(r"ch[oơ]\s+(\d+)\s+nguoi", normalized):
            return f"chở {match.group(1)} người"
        return "chở quá số người quy định"
    if action == "di_sai_lan":
        return "đi sai làn đường"
    if action == "qua_toc_do":
        if km_value is not None:
            km_text = int(km_value) if km_value.is_integer() else km_value
            return f"chạy quá tốc độ {km_text} km/h"
        return "chạy quá tốc độ"
    if km_value is not None and any(keyword in normalized for keyword in SPEED_KEYWORDS):
        km_text = int(km_value) if km_value.is_integer() else km_value
        return f"chạy quá tốc độ {km_text} km/h"
    return None


def build_effective_legal_question(current_question: str, history: List[Dict[str, str]]) -> Dict[str, object]:
    original_question = (current_question or "").strip()
    normalized_question = normalize_legal_text(original_question)

    current_vehicle = detect_vehicle_type(normalized_question)
    current_query_km = extract_km(normalized_question)
    current_action = detect_legal_action(normalized_question)
    followup = is_followup_question(normalized_question)

    inherited_vehicle = infer_vehicle_from_history(history) if (followup or current_vehicle == "khac") else "khac"
    inherited_action = infer_action_from_history(history) if (followup or current_action is None) else None

    effective_vehicle = current_vehicle if current_vehicle != "khac" else inherited_vehicle
    effective_action = current_action or inherited_action

    has_enough_current_context = current_vehicle != "khac" and (
        current_action is not None or current_query_km is not None
    )

    effective_question = original_question
    if followup or not has_enough_current_context:
        parts: List[str] = []
        vehicle_phrase = _vehicle_phrase(effective_vehicle)
        action_phrase = _action_phrase(effective_action, original_question, current_query_km)

        if vehicle_phrase:
            parts.append(f"Đối với {vehicle_phrase}")
        if action_phrase:
            parts.append(action_phrase)

        if not action_phrase and original_question:
            cleaned = original_question.rstrip(" ?")
            if cleaned:
                parts.append(cleaned)

        if parts:
            effective_question = ", ".join(parts) + " bị phạt bao nhiêu?"
            effective_question = re.sub(r"\s+", " ", effective_question).strip()
        else:
            effective_question = original_question

    return {
        "original_question": original_question,
        "effective_question": effective_question,
        "vehicle_type": effective_vehicle if effective_vehicle in VEHICLE_TYPES else "khac",
        "query_km": current_query_km,
        "action": effective_action,
        "is_followup": followup,
        "normalized_question": normalized_question,
    }
