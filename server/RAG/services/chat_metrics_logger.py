import csv
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    "detected_vehicle_type",
    "intent",
    "action",
    "query_km",
    "used_global_docs",
    "global_doc_hits",
    "global_doc_top_score",
    "legal_results",
    "candidate_results",
    "final_hits",
    "km_match_count",
    "intent_match_count",
    "topic_mismatch",
    "final_fallback_reason",
    "rpc_selected",
    "rerouted_from_general_to_legal",
    "retrieval_skipped",
    "primary_ids",
    "source_labels",
    "contexts",
    "reference_answer",
    "gold_ids",
    "ground_truth",
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_relevancy",
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
            with self.output_path.open("a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)

    def _build_row(self, *, request: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
        debug = response.get("debug") or {}
        meta = response.get("meta") or {}
        evaluation = response.get("evaluation") or {}
        timings = evaluation.get("timings") or {}
        hits = evaluation.get("hits") or []

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": response.get("session_id") or request.get("session_id"),
            "route": response.get("route"),
            "question": request.get("question"),
            "effective_question": meta.get("effective_question") or debug.get("effective_question"),
            "answer": response.get("answer"),
            "used_fallback": response.get("used_fallback"),
            "answer_insufficient": self._is_insufficient(response),
            "source_count": meta.get("source_count", len(response.get("sources") or [])),
            "latency_ms": timings.get("latency_ms"),
            "retrieval_time_ms": timings.get("retrieval_time_ms"),
            "rerank_time_ms": timings.get("rerank_time_ms"),
            "gen_time_ms": timings.get("gen_time_ms"),
            "detected_vehicle_type": meta.get("detected_vehicle_type") or evaluation.get("detected_vehicle_type"),
            "intent": meta.get("intent") or debug.get("intent"),
            "action": meta.get("action") or debug.get("action"),
            "query_km": meta.get("query_km") or debug.get("query_km"),
            "used_global_docs": debug.get("used_global_docs"),
            "global_doc_hits": debug.get("global_doc_hits"),
            "global_doc_top_score": debug.get("global_doc_top_score"),
            "legal_results": debug.get("legal_results"),
            "candidate_results": debug.get("candidate_results"),
            "final_hits": debug.get("final_hits"),
            "km_match_count": debug.get("km_match_count"),
            "intent_match_count": debug.get("intent_match_count"),
            "topic_mismatch": debug.get("topic_mismatch"),
            "final_fallback_reason": debug.get("final_fallback_reason"),
            "rpc_selected": debug.get("rpc_selected"),
            "rerouted_from_general_to_legal": meta.get("rerouted_from_general_to_legal"),
            "retrieval_skipped": meta.get("retrieval_skipped"),
            "primary_ids": self._json([item.get("primary_id") for item in hits]),
            "source_labels": self._json([item.get("label") for item in hits]),
            "contexts": self._json([item.get("content") for item in hits]),
            "reference_answer": "",
            "gold_ids": "",
            "ground_truth": "",
            "context_precision": self._ragas_metric(evaluation, "context_precision"),
            "context_recall": self._ragas_metric(evaluation, "context_recall"),
            "faithfulness": self._ragas_metric(evaluation, "faithfulness"),
            "answer_relevancy": self._ragas_metric(evaluation, "answer_relevancy"),
        }

    def _is_insufficient(self, response: Dict[str, Any]) -> Optional[bool]:
        meta = response.get("meta") or {}
        if "answer_insufficient" in meta:
            return meta.get("answer_insufficient")
        answer = str(response.get("answer") or "").lower()
        if not answer:
            return None
        return "chua du can cu" in answer or "chưa đủ căn cứ" in answer

    def _ragas_metric(self, evaluation: Dict[str, Any], key: str) -> Any:
        ragas = evaluation.get("ragas") or {}
        if key in ragas:
            return ragas.get(key)
        return evaluation.get(key)

    def _json(self, value: List[Any]) -> str:
        return json.dumps(value, ensure_ascii=False)


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
