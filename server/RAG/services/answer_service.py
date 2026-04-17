import json
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config.settings import RAGSettings
from prompts.answer_prompts import ANSWER_SYSTEM_PROMPT, INSUFFICIENT_CONTEXT_PROMPT


logger = logging.getLogger("ANSWER_SERVICE")


class AnswerService:
    def __init__(self, settings: RAGSettings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def assess_context(self, question: str, hits: List[Dict[str, Any]], min_score: float, min_evidence: int) -> Dict[str, Any]:
        if len(hits) < min_evidence:
            return {"insufficient_context": True, "reason": "not_enough_evidence"}
        if not hits or float(hits[0].get("hybrid_score", 0.0)) < min_score:
            return {"insufficient_context": True, "reason": "top_score_below_threshold"}

        compact_context = []
        for item in hits[:3]:
            compact_context.append(
                {
                    "label": item.get("label"),
                    "type": item.get("source_type"),
                    "score": item.get("hybrid_score"),
                    "content": (item.get("content") or "")[:800],
                }
            )

        try:
            response = self.client.chat.completions.create(
                model=self.settings.answer_model_name,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": INSUFFICIENT_CONTEXT_PROMPT},
                    {"role": "user", "content": json.dumps({"question": question, "context": compact_context}, ensure_ascii=False)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            logger.warning("insufficient_context evaluator failed: %s", exc)
            return {"insufficient_context": False, "reason": "heuristic_pass"}

    def generate_answer(
        self,
        question: str,
        hits: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        selected_hits = list(hits[:3])
        context_blocks = []
        sources = []
        for index, item in enumerate(selected_hits, start=1):
            context_blocks.append(
                f"[CAN_CU_{index}] [{item.get('source_type')}] {item.get('label')}\n"
                f"URL: {item.get('url') or 'null'}\n"
                f"Score: {item.get('hybrid_score')}\n"
                f"Noi dung: {item.get('content')}"
            )
            sources.append(
                {
                    "type": item.get("source_type"),
                    "label": item.get("label"),
                    "url": item.get("url"),
                }
            )

        messages: List[Dict[str, str]] = [{"role": "system", "content": ANSWER_SYSTEM_PROMPT}]
        for item in history or []:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Cau hoi:\n{question}\n\n"
                    "Hay tra loi chi dua tren cac can cu duoi day. "
                    "Neu khong co can cu khop truc tiep, hay noi ro chua du can cu.\n\n"
                    f"Context retrieve duoc:\n\n" + "\n\n".join(context_blocks)
                ),
            }
        )

        completion = self.client.chat.completions.create(
            model=self.settings.answer_model_name,
            temperature=0,
            messages=messages,
        )
        answer = completion.choices[0].message.content or "Chua tao duoc cau tra loi."
        logger.info("answer service output | answer=%s", answer[:500])
        return {"answer": answer, "sources": sources}
