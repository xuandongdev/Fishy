import json
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set

from openai import OpenAI

from config.settings import RAGSettings
from prompts.answer_prompts import ANSWER_SYSTEM_PROMPT
from services.source_formatter import format_user_facing_source

logger = logging.getLogger("ANSWER_SERVICE")

SAFE_INSUFFICIENT_ANSWER = "Chưa đủ căn cứ trong dữ liệu retrieve được để kết luận chính xác."
EXACT_INTENTS = {"muc_phat", "can_cu_phap_ly", "tuoc_gplx", "tam_giu_phuong_tien"}
SPEED_HINT_RE = re.compile(r"\b(toc do|qua toc do|vuot toc do|km/h|kmh|\d+\s*km)\b", re.I)
MONEY_RE = re.compile(r"\b\d{1,3}(?:[\.,]\d{3})+(?:\s*(?:dong|vnd))?\b", re.I)
DECREE_RE = re.compile(r"\bnghi dinh\s*\d+/\d+/nd-cp\b", re.I)
ARTICLE_RE = re.compile(r"\bdieu\s*\d+\b", re.I)
CLAUSE_RE = re.compile(r"\bkhoan\s*\d+\b", re.I)
POINT_RE = re.compile(r"\bdiem\s*[a-zd]\b", re.I)
SOURCE_TOKEN_LINE_RE = re.compile(r"(?im)^[ \t]*ngu[oôồốỗộơờớởỡợ]n\s*:\s*\[NGUON_\d+\]\s*$")
SOURCE_TOKEN_RE = re.compile(r"\[NGUON_\d+\]")
INSUFFICIENT_SIGNAL_PATTERNS = (
    re.compile(r"\b(chua|khong)\s+du\s+can\s+cu\b", re.I),
    re.compile(r"\bdu\s+lieu\b.*\b(ket\s+luan|xac\s+dinh)\b", re.I),
    re.compile(r"\b(khong|chua)\s+the\s+(ket\s+luan|xac\s+dinh)\s+(chinh\s+xac|chac\s+chan)\b", re.I),
    re.compile(r"\bkho\s+du\s+lieu\b", re.I),
)


class AnswerService:
    def __init__(self, settings: RAGSettings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def assess_context(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        min_score: float,
        min_evidence: int,
        debug_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        debug_meta = debug_meta or {}
        intent = str(debug_meta.get("intent") or "")
        action = str(debug_meta.get("action") or "")
        query_km = debug_meta.get("query_km")
        topic_mismatch = bool(debug_meta.get("topic_mismatch"))
        min_score = float(debug_meta.get("min_score_override") or min_score)
        min_evidence = int(debug_meta.get("min_evidence_override") or min_evidence)
        has_uploaded_doc = any(item.get("source_type") in {"user_upload", "admin_upload"} for item in hits)

        if len(hits) < min_evidence:
            return {"insufficient_context": True, "reason": "not_enough_evidence"}

        above_threshold = [
            item for item in hits if float(item.get("hybrid_score") or item.get("score") or 0.0) >= float(min_score)
        ]
        if len(above_threshold) < min_evidence:
            return {"insufficient_context": True, "reason": "score_below_threshold"}

        if topic_mismatch:
            return {"insufficient_context": True, "reason": "topic_mismatch"}

        if intent in EXACT_INTENTS and not has_uploaded_doc and not any(item.get("source_type") == "legal_db" for item in hits):
            return {"insufficient_context": True, "reason": "exact_query_without_legal_hit"}

        if query_km is not None and action == "qua_toc_do":
            km_supported = [
                item
                for item in hits[:3]
                if item.get("km_phu_hop") is True
                or self._hit_supports_speed(item, float(query_km), require_exact_range=True)
            ]
            if not km_supported:
                return {"insufficient_context": True, "reason": "speed_range_not_supported"}

        return {"insufficient_context": False, "reason": "heuristic_pass"}

    def generate_answer(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None,
        effective_question: Optional[str] = None,
        debug_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        selected_hits = list(hits[:3])
        sources: List[Dict[str, Any]] = []
        debug_meta = debug_meta or {}
        reason = "ok"
        insufficient_context = False

        if not selected_hits:
            return {
                "answer": SAFE_INSUFFICIENT_ANSWER,
                "sources": [],
                "insufficient_context": True,
                "reason": "no_selected_hits",
            }

        context_blocks: List[str] = []
        for index, item in enumerate(selected_hits, start=1):
            context_blocks.append(self._build_context_block(index, item))
            sources.append(
                {
                    "label": self._format_source_label(item),
                    "url": item.get("url"),
                    "ten_van_ban": item.get("ten_van_ban") or item.get("title"),
                    "so_hieu": item.get("so_hieu"),
                    "trang_thai": item.get("trang_thai"),
                    "filename": item.get("filename"),
                    "section_path": item.get("section_path"),
                    "page_start": item.get("page_start"),
                    "page_end": item.get("page_end"),
                }
            )

        evidence = self.assess_context(
            question=effective_question or question,
            hits=selected_hits,
            min_score=float(debug_meta.get("min_score_override") or self.settings.rag_legal_score_threshold),
            min_evidence=int(
                debug_meta.get("min_evidence_override")
                or (1 if str(debug_meta.get("intent") or "") == "giai_thich_chung" else self.settings.rag_min_legal_evidence)
            ),
            debug_meta=debug_meta,
        )
        if evidence["insufficient_context"]:
            logger.info("evidence gate failed | reason=%s", evidence["reason"])
            return {
                "answer": SAFE_INSUFFICIENT_ANSWER,
                "sources": sources,
                "insufficient_context": True,
                "reason": evidence["reason"],
            }

        if self._should_block_answer(selected_hits=selected_hits, debug_meta=debug_meta):
            logger.info(
                "answer blocked | reason=insufficient_speed_evidence | effective_question=%s",
                (effective_question or question)[:300],
            )
            return {
                "answer": SAFE_INSUFFICIENT_ANSWER,
                "sources": sources,
                "insufficient_context": True,
                "reason": "insufficient_speed_evidence",
            }

        history_text = self._history_text(history or [])
        prompt_payload = {
            "original_question": question,
            "effective_question": effective_question or question,
            "history": history_text,
            "context": "\n\n".join(context_blocks),
            "debug": debug_meta,
            "rules": {
                "only_use_context": True,
                "never_invent_legal_citation": True,
                "if_insufficient_say_so": True,
                "cite_source_token": False,
            },
        }

        try:
            response = self.client.chat.completions.create(
                model=self.settings.answer_model_name,
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": self._system_prompt(),
                    },
                    {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
                ],
            )
            answer = (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.warning("answer generation failed, using safe fallback: %s", exc)
            answer = ""
            insufficient_context = True
            reason = "model_generation_failed"

        if answer and not self._answer_supported_by_context(answer, selected_hits):
            logger.warning("answer rejected | reason=unsupported_context | answer=%s", answer[:500])
            answer = ""
            insufficient_context = True
            reason = "unsupported_context"

        if not answer:
            fallback = self._fallback_answer(question=question, hits=selected_hits, debug_meta=debug_meta)
            answer = fallback["answer"]
            insufficient_context = fallback["insufficient_context"] or insufficient_context
            if reason == "ok":
                reason = fallback["reason"]

        answer = self._sanitize_answer(answer)
        if self.is_insufficient_answer(answer):
            insufficient_context = True
            if reason == "ok":
                reason = "model_reported_insufficient_context"

        logger.info("answer service output | answer=%s", answer[:500])
        return {
            "answer": answer,
            "sources": sources,
            "insufficient_context": insufficient_context or self.is_insufficient_answer(answer),
            "reason": reason,
        }

    def _system_prompt(self) -> str:
        strict_rules = (
            "Ban la tro ly phap luat giao thong. Chi duoc tra loi dua tren CONTEXT da cung cap. "
            "Tuyet doi khong tu them Nghi dinh, Dieu, Khoan, Diem, muc phat hoac thong tin phap ly neu context khong co. "
            "Neu context khong du chac chan, hay noi ro rang la chua du can cu trong du lieu retrieve duoc de ket luan chinh xac. "
            "Neu tra loi duoc, hay tra loi tu nhien, ngan gon, neu can thi nhac can cu phap ly bang ten Dieu/Khoan/Nghi dinh co trong context, khong dung token may moc."
        )
        base = (ANSWER_SYSTEM_PROMPT or "").strip()
        if base:
            return strict_rules + "\n\n" + base
        return strict_rules

    def _should_block_answer(self, selected_hits: List[Dict[str, Any]], debug_meta: Dict[str, Any]) -> bool:
        action = str(debug_meta.get("action") or "")
        query_km = debug_meta.get("query_km")
        if action != "qua_toc_do" or query_km is None:
            return False
        return not any(
            item.get("km_phu_hop") is True or self._hit_supports_speed(item, float(query_km), require_exact_range=True)
            for item in selected_hits
        )

    def _hit_supports_speed(self, item: Dict[str, Any], query_km: float, require_exact_range: bool = False) -> bool:
        text = f"{item.get('label') or ''}\n{item.get('content') or ''}"
        try:
            min_km = item.get("min_km")
            max_km = item.get("max_km")
            if min_km is not None and max_km is not None and float(min_km) <= float(query_km) <= float(max_km):
                return True
        except Exception:
            pass
        if require_exact_range:
            return False
        return bool(SPEED_HINT_RE.search(text))

    def _answer_supported_by_context(self, answer: str, hits: List[Dict[str, Any]]) -> bool:
        normalized_context = self._normalize_text(
            "\n".join((item.get("label") or "") + "\n" + (item.get("content") or "") for item in hits)
        )
        normalized_answer = self._normalize_text(answer)

        context_decrees = self._collect_matches(DECREE_RE, normalized_context)
        answer_decrees = self._collect_matches(DECREE_RE, normalized_answer)
        if any(d not in context_decrees for d in answer_decrees):
            return False

        context_articles = self._collect_matches(ARTICLE_RE, normalized_context)
        answer_articles = self._collect_matches(ARTICLE_RE, normalized_answer)
        if context_articles and any(a not in context_articles for a in answer_articles):
            return False

        context_clauses = self._collect_matches(CLAUSE_RE, normalized_context)
        answer_clauses = self._collect_matches(CLAUSE_RE, normalized_answer)
        if context_clauses and any(c not in context_clauses for c in answer_clauses):
            return False

        context_points = self._collect_matches(POINT_RE, normalized_context)
        answer_points = self._collect_matches(POINT_RE, normalized_answer)
        if context_points and any(p not in context_points for p in answer_points):
            return False

        context_money = self._collect_money_values(normalized_context)
        answer_money = self._collect_money_values(normalized_answer)
        if any(value not in context_money for value in answer_money):
            return False

        return True

    def _collect_matches(self, pattern: re.Pattern[str], text: str) -> Set[str]:
        return {re.sub(r"\s+", " ", m.group(0)).strip().lower() for m in pattern.finditer(text or "")}

    def _collect_money_values(self, text: str) -> Set[str]:
        return {self._normalize_money_token(m.group(0)) for m in MONEY_RE.finditer(text or "")}

    def _normalize_money_token(self, token: str) -> str:
        return re.sub(r"[^\d]", "", token or "")

    def _normalize_text(self, text: str) -> str:
        lowered = (text or "").lower().replace("đ", "d").replace("Đ", "D")
        return re.sub(r"\s+", " ", lowered).strip()

    def _build_context_block(self, index: int, item: Dict[str, Any]) -> str:
        hybrid_score = item.get("hybrid_score") or item.get("score")
        final_score = item.get("final_rerank_score")
        ce_score = item.get("cross_encoder_score")
        min_km = item.get("min_km")
        max_km = item.get("max_km")
        km_match = item.get("km_phu_hop")
        return (
            f"[NGUON_{index}] {self._format_source_label(item)}\n"
            f"URL: {item.get('url') or 'null'}\n"
            f"HybridScore: {hybrid_score}\n"
            f"RerankScore: {final_score}\n"
            f"CrossEncoder: {ce_score}\n"
            f"TenVanBan: {item.get('ten_van_ban') or item.get('title')}\n"
            f"SoHieu: {item.get('so_hieu')}\n"
            f"TrangThai: {item.get('trang_thai')}\n"
            f"FileName: {item.get('filename')}\n"
            f"SectionPath: {item.get('section_path')}\n"
            f"PageStart: {item.get('page_start')}\n"
            f"PageEnd: {item.get('page_end')}\n"
            f"MinKM: {min_km}\n"
            f"MaxKM: {max_km}\n"
            f"KmPhuHop: {km_match}\n"
            f"Noi dung: {item.get('content')}"
        )

    def _format_source_label(self, item: Dict[str, Any]) -> str:
        return format_user_facing_source(item)

    def _sanitize_answer(self, answer: str) -> str:
        cleaned = SOURCE_TOKEN_LINE_RE.sub("", answer or "")
        cleaned = SOURCE_TOKEN_RE.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _history_text(self, history: List[Dict[str, str]]) -> str:
        turns: List[str] = []
        for item in history[-8:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            prefix = "User" if role == "user" else "Assistant"
            turns.append(f"{prefix}: {content}")
        return "\n".join(turns)

    def _fallback_answer(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        debug_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        debug_meta = debug_meta or {}
        best = hits[0] if hits else {}
        content = (best.get("content") or "").strip()
        label = (best.get("label") or "").strip()
        action = str(debug_meta.get("action") or "")
        query_km = debug_meta.get("query_km")
        intent = str(debug_meta.get("intent") or "")

        if not content:
            return {
                "answer": SAFE_INSUFFICIENT_ANSWER,
                "insufficient_context": True,
                "reason": "fallback_no_content",
            }

        if intent in EXACT_INTENTS or (action == "qua_toc_do" and query_km is not None):
            logger.info("fallback skipped | reason=exact_legal_query")
            return {
                "answer": SAFE_INSUFFICIENT_ANSWER,
                "insufficient_context": True,
                "reason": "exact_query_no_safe_fallback",
            }

        excerpt = self._extract_legal_excerpt(content)
        return {
            "answer": f'Noi dung gan nhat retrieve duoc cho cau hoi "{question}" den tu {label} la:\n\n{excerpt}',
            "insufficient_context": False,
            "reason": "excerpt_fallback",
        }

    def _extract_legal_excerpt(self, content: str, max_len: int = 900) -> str:
        lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
        excerpt = "\n".join(lines[:8]).strip()
        excerpt = excerpt[:max_len].strip()
        return excerpt or (content or "")[:max_len].strip()

    def is_insufficient_answer(self, answer: str) -> bool:
        normalized = unicodedata.normalize("NFD", self._normalize_text(answer))
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").replace("đ", "d")
        safe_normalized = unicodedata.normalize("NFD", self._normalize_text(SAFE_INSUFFICIENT_ANSWER))
        safe_normalized = "".join(ch for ch in safe_normalized if unicodedata.category(ch) != "Mn").replace("đ", "d")
        if normalized == safe_normalized:
            return True
        return all(pattern.search(normalized) for pattern in INSUFFICIENT_SIGNAL_PATTERNS[:2]) or any(
            pattern.search(normalized) for pattern in INSUFFICIENT_SIGNAL_PATTERNS
        )
