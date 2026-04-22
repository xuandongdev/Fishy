import csv
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger("CHAT_METRICS_LOGGER")

CSV_FIELDS = [
    "timestamp",
    "session_id",
    "route",
    "question",
    "effective_question",
    "answer",
    "used_fallback",
    "answer_insufficient",
    "source_count",
    "latency_ms",
    "retrieval_time_ms",
    "rerank_time_ms",
    "gen_time_ms",
    "used_global_docs",
    "global_doc_hits",
    "global_doc_top_score",
    "legal_results",
    "candidate_results",
    "final_hits",
    "intent_match_count",
    "topic_mismatch",
    "retrieval_skipped",
]


class ChatMetricsLogger:
    def __init__(self, output_path: str) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log_chat(self, *, request: Dict[str, Any], response: Dict[str, Any]) -> None:
        row = self._build_row(request=request, response=response)
        with self._lock:
            file_exists = self.output_path.exists()
            with self.output_path.open("a", encoding="utf-8", newline="") as file_obj:
                writer = csv.DictWriter(file_obj, fieldnames=CSV_FIELDS)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)

    def _build_row(self, *, request: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        debug = response.get("debug") or {}
        meta = response.get("meta") or {}
        evaluation = response.get("evaluation") or {}
        timings = evaluation.get("timings") or {}

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": response.get("session_id") or request.get("session_id") or "",
            "route": response.get("route") or meta.get("route_selected") or "",
            "question": request.get("question") or "",
            "effective_question": meta.get("effective_question") or debug.get("effective_question") or "",
            "answer": response.get("answer") or "",
            "used_fallback": response.get("used_fallback"),
            "answer_insufficient": self._answer_insufficient(response),
            "source_count": self._coalesce(
                meta.get("source_count"),
                len(response.get("sources") or []),
            ),
            "latency_ms": self._timing(timings, meta, "latency_ms"),
            "retrieval_time_ms": self._timing(timings, meta, "retrieval_time_ms"),
            "rerank_time_ms": self._timing(timings, meta, "rerank_time_ms"),
            "gen_time_ms": self._timing(timings, meta, "gen_time_ms"),
            "used_global_docs": self._coalesce(debug.get("used_global_docs"), meta.get("used_global_docs"), False),
            "global_doc_hits": self._coalesce(debug.get("global_doc_hits"), 0),
            "global_doc_top_score": self._coalesce(debug.get("global_doc_top_score"), 0.0),
            "legal_results": self._coalesce(debug.get("legal_results"), 0),
            "candidate_results": self._coalesce(debug.get("candidate_results"), 0),
            "final_hits": self._coalesce(debug.get("final_hits"), 0),
            "intent_match_count": self._coalesce(debug.get("intent_match_count"), 0),
            "topic_mismatch": self._coalesce(debug.get("topic_mismatch"), False),
            "retrieval_skipped": self._coalesce(meta.get("retrieval_skipped"), False),
        }

    def _timing(self, timings: Dict[str, Any], meta: Dict[str, Any], key: str) -> Any:
        if key in timings and timings.get(key) is not None:
            return timings.get(key)
        return meta.get(key)

    def _answer_insufficient(self, response: Dict[str, Any]) -> Optional[bool]:
        meta = response.get("meta") or {}
        if meta.get("answer_insufficient") is not None:
            return meta.get("answer_insufficient")
        answer = str(response.get("answer") or "").lower()
        if not answer:
            return None
        return "chua du can cu" in answer or "chưa đủ căn cứ" in answer

    def _coalesce(self, *values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None


def safe_log_chat_metrics(
    metrics_logger: Optional[ChatMetricsLogger],
    *,
    request: Dict[str, Any],
    response: Dict[str, Any],
) -> None:
    if metrics_logger is None:
        return
    try:
        metrics_logger.log_chat(request=request, response=response)
    except Exception as exc:
        logger.warning("chat metrics csv logging failed | reason=%s", exc)
