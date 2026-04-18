import re
import unicodedata
from typing import Dict, List, Optional


VEHICLE_TYPES = {"o_to", "xe_may", "xe_dap", "di_bo", "khac"}
LEGAL_INTENTS = {
    "muc_phat",
    "can_cu_phap_ly",
    "tuoc_gplx",
    "tam_giu_phuong_tien",
    "doi_tuong_ap_dung",
    "giai_thich_chung",
    "followup_khong_ro",
}

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
    "vay",
)

SPEED_KEYWORDS = (
    "qua toc do",
    "vuot toc do",
    "chay qua",
    "toc do",
    "km/h",
    "km",
    "cay",
)

ACTION_PATTERNS = {
    "vuot_den_do": [
        r"vuot den do",
        r"khong chap hanh hieu lenh den tin hieu",
        r"den do",
    ],
    "qua_toc_do": [
        r"qua toc do",
        r"vuot toc do",
        r"chay qua",
        r"toc do",
        r"km/h",
        r"km",
        r"cay",
    ],
    "nong_do_con": [
        r"nong do con",
        r"\bcon\b",
        r"bia ruou",
    ],
    "khong_doi_mu": [
        r"khong doi mu",
        r"khong doi mu bao hiem",
        r"mu bao hiem",
    ],
    "cho_qua_nguoi": [
        r"cho qua",
        r"qua so nguoi",
        r"cho ba",
        r"cho bon",
    ],
    "di_sai_lan": [
        r"sai lan",
        r"khong dung lan",
        r"lan duong",
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
    re.compile(r"(?:qua|vuot|chay)?\s*(?:toc do)?\s*(\d+(?:[\.,]\d+)?)\s*(?:km/h|kmh|km|cay)\b"),
    re.compile(r"(?:qua|vuot)\s*(\d+(?:[\.,]\d+)?)\b"),
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


def detect_legal_intent(query: str) -> str:
    q = normalize_legal_text(query)
    if not q:
        return "followup_khong_ro"
    if re.search(r"\b(phat bao nhieu|muc phat|bao nhieu tien|phat sao|bi phat bao nhieu)\b", q):
        return "muc_phat"
    if re.search(r"\b(can cu|dieu nao|khoan nao|diem nao|nghi dinh nao|can cu phap ly)\b", q):
        return "can_cu_phap_ly"
    if re.search(r"\b(tuoc|giu bang|giu gplx|tuoc bang|tuoc giay phep lai xe)\b", q):
        return "tuoc_gplx"
    if re.search(r"\b(giu xe|tam giu xe|tam giu phuong tien|giu phuong tien)\b", q):
        return "tam_giu_phuong_tien"
    if re.search(r"\b(ap dung cho ai|doi tuong nao|xe nao|phuong tien nao|truong hop nao)\b", q):
        return "doi_tuong_ap_dung"
    if is_followup_question(q):
        return "followup_khong_ro"
    return "giai_thich_chung"


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
    for preferred_role in ("user", "assistant"):
        for item in reversed(history or []):
            if item.get("role") != preferred_role:
                continue
            detected = detect_vehicle_type(item.get("content") or "")
            if detected != "khac":
                return detected
    return "khac"


def infer_action_from_history(history: List[Dict[str, str]]) -> Optional[str]:
    for preferred_role in ("user", "assistant"):
        for item in reversed(history or []):
            if item.get("role") != preferred_role:
                continue
            action = detect_legal_action(item.get("content") or "")
            if action:
                return action
    return None


def infer_intent_from_history(history: List[Dict[str, str]]) -> str:
    for preferred_role in ("user", "assistant"):
        for item in reversed(history or []):
            if item.get("role") != preferred_role:
                continue
            intent = detect_legal_intent(item.get("content") or "")
            if intent != "followup_khong_ro":
                return intent
    return "followup_khong_ro"


def _vehicle_phrase(vehicle_type: str) -> Optional[str]:
    return VEHICLE_TYPE_TO_PHRASE.get(vehicle_type)


def _action_phrase(action: Optional[str], question: str, km_value: Optional[float]) -> Optional[str]:
    normalized = normalize_legal_text(question)
    if action == "vuot_den_do":
        return "vuot den do"
    if action == "nong_do_con":
        return "vi pham nong do con"
    if action == "khong_doi_mu":
        return "khong doi mu bao hiem"
    if action == "cho_qua_nguoi":
        if match := re.search(r"cho\s+(\d+)\s+nguoi", normalized):
            return f"cho {match.group(1)} nguoi"
        return "cho qua so nguoi quy dinh"
    if action == "di_sai_lan":
        return "di sai lan duong"
    if action == "qua_toc_do":
        if km_value is not None:
            km_text = int(km_value) if km_value.is_integer() else km_value
            return f"chay qua toc do {km_text} km/h"
        return "chay qua toc do"
    if km_value is not None and any(keyword in normalized for keyword in SPEED_KEYWORDS):
        km_text = int(km_value) if km_value.is_integer() else km_value
        return f"chay qua toc do {km_text} km/h"
    return None


def _intent_suffix(intent: str, original_question: str) -> str:
    if intent == "muc_phat":
        return "bi phat bao nhieu?"
    if intent == "can_cu_phap_ly":
        return "can cu phap ly la gi?"
    if intent == "tuoc_gplx":
        return "co bi tuoc gplx khong?"
    if intent == "tam_giu_phuong_tien":
        return "co bi tam giu phuong tien khong?"
    return original_question.strip()


def build_effective_legal_question(current_question: str, history: List[Dict[str, str]]) -> Dict[str, object]:
    original_question = (current_question or "").strip()
    normalized_question = normalize_legal_text(original_question)

    current_vehicle = detect_vehicle_type(normalized_question)
    current_query_km = extract_km(normalized_question)
    current_action = detect_legal_action(normalized_question)
    current_intent = detect_legal_intent(normalized_question)
    followup = is_followup_question(normalized_question)

    inherited_vehicle = infer_vehicle_from_history(history) if (followup or current_vehicle == "khac") else "khac"
    inherited_action = infer_action_from_history(history) if (followup or current_action is None) else None
    inherited_intent = (
        infer_intent_from_history(history) if (followup or current_intent == "followup_khong_ro") else "followup_khong_ro"
    )

    effective_vehicle = current_vehicle if current_vehicle != "khac" else inherited_vehicle
    effective_action = current_action or inherited_action
    effective_intent = current_intent if current_intent != "followup_khong_ro" else inherited_intent

    has_enough_current_context = current_vehicle != "khac" and (
        current_action is not None or current_query_km is not None
    )

    effective_question = original_question
    rewrite_confidence = 0.2
    if has_enough_current_context and not followup:
        rewrite_confidence = 0.9
    else:
        parts: List[str] = []
        vehicle_phrase = _vehicle_phrase(effective_vehicle)
        action_phrase = _action_phrase(effective_action, original_question, current_query_km)

        if vehicle_phrase and (followup or current_vehicle == "khac"):
            parts.append(vehicle_phrase)
            rewrite_confidence += 0.25
        if action_phrase and (followup or current_action is None):
            parts.append(action_phrase)
            rewrite_confidence += 0.35
        if effective_intent != "followup_khong_ro":
            rewrite_confidence += 0.15

        if parts and rewrite_confidence >= 0.6:
            suffix = _intent_suffix(effective_intent, original_question)
            if suffix == original_question.strip():
                effective_question = f"{', '.join(parts)}; {original_question}".strip()
            else:
                effective_question = f"{', '.join(parts)} {suffix}".strip()
            effective_question = re.sub(r"\s+", " ", effective_question).strip()
        else:
            effective_question = original_question
            rewrite_confidence = min(rewrite_confidence, 0.55)

    return {
        "original_question": original_question,
        "effective_question": effective_question,
        "vehicle_type": effective_vehicle if effective_vehicle in VEHICLE_TYPES else "khac",
        "query_km": current_query_km,
        "intent": effective_intent if effective_intent in LEGAL_INTENTS else "followup_khong_ro",
        "action": effective_action,
        "is_followup": followup,
        "rewrite_confidence": round(rewrite_confidence, 2),
        "normalized_question": normalized_question,
    }
