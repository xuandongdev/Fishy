import json
import logging
from typing import Any, Dict, List

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

    def generate_answer(self, question: str, hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        context_blocks = []
        sources = []
        for item in hits:
            context_blocks.append(
                f"[{item.get('source_type')}] {item.get('label')}\nURL: {item.get('url') or 'null'}\nScore: {item.get('hybrid_score')}\n{item.get('content')}"
            )
            sources.append(
                {
                    "type": item.get("source_type"),
                    "label": item.get("label"),
                    "url": item.get("url"),
                }
            )

        completion = self.client.chat.completions.create(
            model=self.settings.answer_model_name,
            temperature=0.2,
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Cau hoi:\n{question}\n\n"
                        f"Context retrieve duoc:\n\n" + "\n\n".join(context_blocks)
                    ),
                },
            ],
        )
        answer = completion.choices[0].message.content or "Chua tao duoc cau tra loi."
        return {"answer": answer, "sources": sources}
