import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from openai import OpenAI

from config.settings import RAGSettings
from prompts.answer_prompts import ANSWER_SYSTEM_PROMPT, INSUFFICIENT_CONTEXT_PROMPT

logger = logging.getLogger("ANSWER_SERVICE")

SPEED_HINT_RE = re.compile(r"\b(toc do|qu[aá]\s*toc\s*do|vuot\s*toc\s*do|km/h|kmh|\d+\s*km)\b", re.I)
MONEY_RE = re.compile(r"\b\d{1,3}(?:[\.,]\d{3})+(?:\s*đồng|\s*dong)?\b", re.I)
DECREE_RE = re.compile(r"Nghị\s*định\s*\d+\/\d+\/NĐ-CP", re.I)
ARTICLE_RE = re.compile(r"Điều\s*\d+", re.I)
CLAUSE_RE = re.compile(r"Khoản\s*\d+", re.I)
POINT_RE = re.compile(r"Điểm\s*[a-zđ]\b", re.I)


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
    ) -> Dict[str, Any]:
        if len(hits) < min_evidence:
            return {"insufficient_context": True, "reason": "not_enough_evidence"}
        above_threshold = [
            item for item in hits if float(item.get("hybrid_score") or item.get("score") or 0.0) >= float(min_score)
        ]
        if len(above_threshold) < min_evidence:
            return {"insufficient_context": True, "reason": "score_below_threshold"}
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

        if not selected_hits:
            return {"answer": INSUFFICIENT_CONTEXT_PROMPT.strip(), "sources": []}

        context_blocks: List[str] = []
        for index, item in enumerate(selected_hits, start=1):
            context_blocks.append(self._build_context_block(index, item))
            sources.append(
                {
                    "type": item.get("source_type"),
                    "label": item.get("label"),
                    "url": item.get("url"),
                }
            )

        if self._should_block_answer(selected_hits=selected_hits, debug_meta=debug_meta):
            answer = INSUFFICIENT_CONTEXT_PROMPT.strip()
            logger.info(
                "answer blocked | reason=insufficient_speed_evidence | effective_question=%s",
                (effective_question or question)[:300],
            )
            logger.info("answer service output | answer=%s", answer[:500])
            return {"answer": answer, "sources": sources}

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
                "cite_source_token": True,
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
            logger.warning("answer generation failed, fallback to extractive summary: %s", exc)
            answer = ""

        if answer and not self._answer_supported_by_context(answer, selected_hits):
            logger.warning("answer rejected | reason=unsupported_context | answer=%s", answer[:500])
            answer = ""

        if not answer:
            answer = self._fallback_answer(question=question, hits=selected_hits, debug_meta=debug_meta)

        logger.info("answer service output | answer=%s", answer[:500])
        return {"answer": answer, "sources": sources}

    def _system_prompt(self) -> str:
        strict_rules = (
            "Bạn là trợ lý pháp luật giao thông. Chỉ được trả lời dựa trên CONTEXT đã cung cấp. "
            "Tuyệt đối không tự thêm Nghị định, Điều, Khoản, Điểm, mức phạt hoặc năm văn bản nếu chúng không xuất hiện rõ trong CONTEXT. "
            "Nếu CONTEXT không đủ chắc chắn để kết luận, hãy nói rõ là chưa đủ căn cứ trong dữ liệu retrieve được. "
            "Nếu trả lời được, hãy nêu ngắn gọn kết luận và căn cứ gần nhất bằng token dạng [CAN_CU_1], [CAN_CU_2]..."
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
        return not any(self._hit_supports_speed(item, query_km) for item in selected_hits)

    def _hit_supports_speed(self, item: Dict[str, Any], query_km: float) -> bool:
        text = f"{item.get('label') or ''}\n{item.get('content') or ''}"
        try:
            min_km = item.get("min_km")
            max_km = item.get("max_km")
            if min_km is not None and max_km is not None and float(min_km) <= float(query_km) <= float(max_km):
                return True
        except Exception:
            pass
        return bool(SPEED_HINT_RE.search(text))

    def _answer_supported_by_context(self, answer: str, hits: List[Dict[str, Any]]) -> bool:
        normalized_context = "\n".join((item.get("label") or "") + "\n" + (item.get("content") or "") for item in hits)
        context_decrees = self._collect_matches(DECREE_RE, normalized_context)
        answer_decrees = self._collect_matches(DECREE_RE, answer)
        unsupported_decrees = [d for d in answer_decrees if d not in context_decrees]
        if unsupported_decrees:
            logger.warning("unsupported decree(s) in answer: %s", unsupported_decrees)
            return False

        context_articles = self._collect_matches(ARTICLE_RE, normalized_context)
        answer_articles = self._collect_matches(ARTICLE_RE, answer)
        unsupported_articles = [a for a in answer_articles if a not in context_articles]
        if unsupported_articles and context_articles:
            logger.warning("unsupported article(s) in answer: %s", unsupported_articles)
            return False

        context_clauses = self._collect_matches(CLAUSE_RE, normalized_context)
        answer_clauses = self._collect_matches(CLAUSE_RE, answer)
        unsupported_clauses = [c for c in answer_clauses if c not in context_clauses]
        if unsupported_clauses and context_clauses:
            logger.warning("unsupported clause(s) in answer: %s", unsupported_clauses)
            return False

        context_points = self._collect_matches(POINT_RE, normalized_context)
        answer_points = self._collect_matches(POINT_RE, answer)
        unsupported_points = [p for p in answer_points if p not in context_points]
        if unsupported_points and context_points:
            logger.warning("unsupported point(s) in answer: %s", unsupported_points)
            return False

        if MONEY_RE.search(answer) and not MONEY_RE.search(normalized_context):
            logger.warning("answer includes money not present in context")
            return False

        return True

    def _collect_matches(self, pattern: re.Pattern[str], text: str) -> Set[str]:
        return {re.sub(r"\s+", " ", m.group(0)).strip().lower() for m in pattern.finditer(text or "")}

    def _build_context_block(self, index: int, item: Dict[str, Any]) -> str:
        hybrid_score = item.get("hybrid_score") or item.get("score")
        final_score = item.get("final_rerank_score")
        ce_score = item.get("cross_encoder_score")
        min_km = item.get("min_km")
        max_km = item.get("max_km")
        return (
            f"[CAN_CU_{index}] [{item.get('source_type')}] {item.get('label')}\n"
            f"URL: {item.get('url') or 'null'}\n"
            f"HybridScore: {hybrid_score}\n"
            f"RerankScore: {final_score}\n"
            f"CrossEncoder: {ce_score}\n"
            f"MinKM: {min_km}\n"
            f"MaxKM: {max_km}\n"
            f"Noi dung: {item.get('content')}"
        )

    def _history_text(self, history: List[Dict[str, str]]) -> str:
        turns: List[str] = []
        for item in history[-6:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            prefix = "User" if role == "user" else "Assistant"
            turns.append(f"{prefix}: {content}")
        return "\n".join(turns)

    def _fallback_answer(self, question: str, hits: List[Dict[str, Any]], debug_meta: Optional[Dict[str, Any]] = None) -> str:
        debug_meta = debug_meta or {}
        best = hits[0] if hits else {}
        content = (best.get("content") or "").strip()
        label = (best.get("label") or "").strip()
        action = str(debug_meta.get("action") or "")
        query_km = debug_meta.get("query_km")

        if not content:
            return INSUFFICIENT_CONTEXT_PROMPT.strip()

        if action == "qua_toc_do" and query_km is not None:
            if self._hit_supports_speed(best, float(query_km)):
                excerpt = self._extract_legal_excerpt(content)
                return (
                    f"Theo dữ liệu retrieve được, căn cứ gần nhất là {label}. "
                    f"Nội dung liên quan đến hành vi chạy quá tốc độ là:\n\n{excerpt}\n\nNguồn: [CAN_CU_1]"
                )
            return INSUFFICIENT_CONTEXT_PROMPT.strip()

        excerpt = self._extract_legal_excerpt(content)
        return (
            f"Dựa trên căn cứ gần nhất {label}, nội dung retrieve được cho câu hỏi “{question}” là:\n\n"
            f"{excerpt}\n\n"
            f"Nguồn: [CAN_CU_1]"
        )

    def _extract_legal_excerpt(self, content: str, max_len: int = 900) -> str:
        lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
        excerpt = "\n".join(lines[:8]).strip()
        excerpt = excerpt[:max_len].strip()
        return excerpt or (content or "")[:max_len].strip()
