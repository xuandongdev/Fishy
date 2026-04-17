import re
import unicodedata
from typing import Dict, List, Optional


VEHICLE_TYPES = {"o_to", "xe_may", "xe_dap", "di_bo", "khac"}

VEHICLE_TYPE_TO_PHRASE = {
    "xe_may": "xe may",
    "o_to": "o to",
    "xe_dap": "xe dap",
    "di_bo": "nguoi di bo",
}

FOLLOWUP_PREFIXES = (
    "vay con",
    "the con",
    "the neu",
    "neu vay",
    "con",
    "neu",
    "truong hop do",
    "truong hop nay",
    "truong hop ay",
    "the sao",
    "thi sao",
)

GENERAL_CHAT_KEYWORDS = (
    "xin chao",
    "chao",
    "hello",
    "hi",
    "ban la ai",
    "ban ten gi",
    "cam on",
    "thank you",
    "tam biet",
    "bye",
)


def normalize_legal_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").strip().lower())
    ascii_text = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", ascii_text).strip()


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


def extract_km(query: str) -> Optional[float]:
    q = normalize_legal_text(query)
    patterns = (
        r"(\d+(?:[\.,]\d+)?)\s*(?:km/h|kmh|km|cay so|cay)\b",
        r"(?:qua toc do|chay qua|vuot qua|vuot|qua|muc|toc do)\s*(\d+(?:[\.,]\d+)?)\b",
    )

    for pattern in patterns:
        match = re.search(pattern, q, re.IGNORECASE)
        if not match:
            continue
        raw_value = match.group(1)
        if not raw_value:
            continue
        try:
            return float(raw_value.replace(",", "."))
        except ValueError:
            return None
    return None


def detect_legal_action(query: str) -> Optional[str]:
    q = normalize_legal_text(query)
    km = extract_km(q)

    if "vuot den do" in q or ("den do" in q and "vuot" in q):
        return "vuot den do"
    if "dua xe" in q:
        return "dua xe"
    if "nong do con" in q or "ruou bia" in q or "uon ruou" in q:
        return "vi pham nong do con"
    if km is not None or "toc do" in q or "chay qua" in q or "vuot toc do" in q:
        return "chay qua toc do"
    if re.search(r"\bcho\s*(3|ba|4|bon)\b", q):
        return "cho qua so nguoi quy dinh"
    if "vuot" in q and "den" in q:
        return "vuot den"
    return None


def is_followup_question(question: str) -> bool:
    normalized = normalize_legal_text(question)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) or normalized == prefix for prefix in FOLLOWUP_PREFIXES):
        return True
    if len(normalized.split()) <= 7 and (
        extract_km(normalized) is not None or
        normalized.endswith("thi sao") or
        normalized.endswith("thi phat sao") or
        normalized.endswith("thi bi phat bao nhieu")
    ):
        return True
    return False


def looks_like_legal_question(question: str) -> bool:
    normalized = normalize_legal_text(question)
    heuristic_tokens = (
        "phat",
        "bao nhieu",
        "co bi",
        "vuot den do",
        "den do",
        "toc do",
        "dua xe",
        "nong do con",
        "gplx",
        "giay to",
        "xe may",
        "o to",
        "nguoi di bo",
    )
    return any(token in normalized for token in heuristic_tokens) or extract_km(normalized) is not None


def history_suggests_legal(history: List[Dict[str, str]]) -> bool:
    recent_history = history[-8:]
    for item in recent_history:
        normalized = normalize_legal_text(item.get("content", ""))
        if looks_like_legal_question(normalized):
            return True
        if any(token in normalized for token in ("can cu", "nguon: legal_db", "nghi dinh", "xu phat", "muc phat")):
            return True
    return False


def infer_vehicle_from_history(history: List[Dict[str, str]]) -> str:
    for item in reversed(history[-10:]):
        vehicle_type = detect_vehicle_type(item.get("content", ""))
        if vehicle_type != "khac":
            return vehicle_type
    return "khac"


def infer_action_from_history(history: List[Dict[str, str]]) -> Optional[str]:
    for item in reversed(history[-10:]):
        action = detect_legal_action(item.get("content", ""))
        if action:
            return action
    return None


def _build_action_phrase(action: Optional[str], query_km: Optional[float], original_question: str) -> Optional[str]:
    normalized = normalize_legal_text(original_question)
    if action == "chay qua toc do":
        if query_km is not None:
            return f"chay qua toc do {int(query_km) if query_km.is_integer() else query_km} km/h"
        return "chay qua toc do"
    if action == "vuot den do":
        return "vuot den do"
    if action == "dua xe":
        return "dua xe"
    if action == "vi pham nong do con":
        return "vi pham nong do con"
    if action == "cho qua so nguoi quy dinh":
        match = re.search(r"\bcho\s*(\d+|ba|bon)\b", normalized)
        if match:
            raw_count = match.group(1)
            if raw_count == "ba":
                raw_count = "3"
            if raw_count == "bon":
                raw_count = "4"
            return f"cho {raw_count} nguoi"
        return "cho qua so nguoi quy dinh"
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

    if not followup and has_enough_current_context:
        return {
            "original_question": original_question,
            "effective_question": original_question,
            "detected_vehicle_type": current_vehicle,
            "query_km": current_query_km,
            "detected_action": current_action,
            "is_followup": False,
        }

    action_phrase = _build_action_phrase(effective_action, current_query_km, original_question)
    vehicle_phrase = VEHICLE_TYPE_TO_PHRASE.get(effective_vehicle)

    pieces: List[str] = []
    if vehicle_phrase:
        pieces.append(f"Doi voi {vehicle_phrase}")
    if action_phrase:
        pieces.append(action_phrase)

    if pieces:
        effective_question = ", ".join([pieces[0], " ".join(pieces[1:]).strip()]) if len(pieces) > 1 else pieces[0]
        effective_question = effective_question.strip(", ")
        if "phat" not in normalize_legal_text(original_question):
            effective_question = f"{effective_question} bi phat bao nhieu?"
        else:
            effective_question = f"{effective_question}, {original_question}".strip()
    else:
        effective_question = original_question

    effective_question = re.sub(r"\s+", " ", effective_question).strip(" ,")

    return {
        "original_question": original_question,
        "effective_question": effective_question,
        "detected_vehicle_type": effective_vehicle if effective_vehicle in VEHICLE_TYPES else "khac",
        "query_km": current_query_km,
        "detected_action": effective_action,
        "is_followup": followup,
    }
