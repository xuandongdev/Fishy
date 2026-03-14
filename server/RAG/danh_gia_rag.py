import os
import json
import argparse
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.run_config import RunConfig

from ragas.metrics import Faithfulness, ContextRecall, ContextPrecision
try:
    from ragas.metrics import ResponseRelevancy as RelevancyMetric
except Exception:
    from ragas.metrics import AnswerRelevancy as RelevancyMetric

from supabase import create_client
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from openai import OpenAI
from ragas.llms import llm_factory
from ragas.embeddings import embedding_factory


# =========================
# 1. CẤU HÌNH MÔI TRƯỜNG
# =========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.45"))
MATCH_COUNT = int(os.getenv("MATCH_COUNT", "5"))
OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY trong file .env")

if not OPENAI_API_KEY:
    print("CẢNH BÁO: Chưa tìm thấy OPENAI_API_KEY trong .env. Phần judge bằng RAGAS/OpenAI có thể không chạy được.")

print("\nĐang khởi tạo Supabase và model embedding E5...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")


# =========================
# 2. RETRIEVER SUPABASE
# =========================
class LegalSupabaseRetriever(BaseRetriever):
    match_threshold: float = MATCH_THRESHOLD
    match_count: int = MATCH_COUNT

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        query_vector = embedding_model.encode(
            "query: " + query,
            normalize_embeddings=True
        ).tolist()

        rpc_res = supabase.rpc(
            "match_legal_docs_v2",
            {
                "vector_truy_van": query_vector,
                "van_ban_truy_van": query,
                "nguong_khop": self.match_threshold,
                "so_luong_ket_qua": self.match_count,
            },
        ).execute()

        docs: List[Document] = []
        for hit in (rpc_res.data or []):
            docs.append(
                Document(
                    page_content=hit.get("noidung", ""),
                    metadata={"sothutund": hit.get("sothutund")},
                )
            )
        return docs


retriever = LegalSupabaseRetriever()
generator_llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.0)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

ragas_llm = llm_factory(OPENAI_JUDGE_MODEL, client=openai_client) if openai_client else None
ragas_emb = (
    embedding_factory("openai", model=OPENAI_EMBED_MODEL, client=openai_client)
    if openai_client else None
)


# =========================
# 3. HÀM TIỆN ÍCH
# =========================
def normalize_question(q: str) -> str:
    return " ".join((q or "").strip().split())


def make_sample_key(item: Dict[str, Any]) -> str:
    return str(item.get("query_id") or normalize_question(item.get("question", "")))


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def append_jsonl(path: str, item: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def build_prompt(question: str, contexts: List[str]) -> str:
    joined_contexts = "\n".join(contexts) if contexts else "Không có ngữ cảnh truy xuất được."
    return f"""Dựa CHỈ vào ngữ cảnh dưới đây để trả lời.

- Nếu câu hỏi hỏi “lỗi gì”, hãy nêu đúng tên lỗi.
- Nếu hỏi có vi phạm không, trả lời ngắn gọn “Có” hoặc “Không”, rồi nêu đúng lỗi nếu có.
- Nếu hỏi mức phạt hoặc tước bằng, nêu đúng mức xử phạt theo ngữ cảnh.
- Không suy diễn ngoài ngữ cảnh.
- Nếu ngữ cảnh không đủ, hãy nói rõ là không đủ căn cứ trong dữ liệu truy xuất.

Ngữ cảnh:
{joined_contexts}

Câu hỏi: {question}

Trả lời:
"""


def compute_retrieval_metrics(gold_ids: List[Any], retrieved_ids: List[Any]) -> Dict[str, Any]:
    gold = [g for g in (gold_ids or []) if g is not None]
    ret = [r for r in (retrieved_ids or []) if r is not None]

    first_rank: Optional[int] = None
    for idx, rid in enumerate(ret, start=1):
        if rid in gold:
            first_rank = idx
            break

    hit_at_k = 1 if first_rank is not None else 0
    recall_at_k = (len(set(gold).intersection(set(ret))) / len(set(gold))) if gold else None
    mrr = (1.0 / first_rank) if first_rank is not None else 0.0

    return {
        "first_relevant_rank": first_rank,
        "hit_at_k": hit_at_k,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
    }


def build_single_sample_dataset(item: Dict[str, Any]) -> Dataset:
    data = {
        # alias cũ
        "question": [item.get("question", "")],
        "answer": [item.get("answer", "")],
        "contexts": [item.get("contexts", [])],
        "ground_truth": [item.get("ground_truth", "")],
        # alias mới
        "user_input": [item.get("question", "")],
        "response": [item.get("answer", "")],
        "retrieved_contexts": [item.get("contexts", [])],
        "reference": [item.get("ground_truth", "")],
    }
    return Dataset.from_dict(data)


# =========================
# 4. GENERATE ONLY
# =========================
def generate_only(eval_file: str, predictions_file: str, limit: Optional[int] = None) -> None:
    eval_items = load_jsonl(eval_file)
    if not eval_items:
        raise FileNotFoundError(f"Không đọc được dữ liệu từ {eval_file}")

    done_items = load_jsonl(predictions_file)
    done_keys = {str(x.get("sample_key")) for x in done_items if x.get("sample_key")}

    total = len(eval_items) if limit is None else min(len(eval_items), limit)
    print(f"\nBẮT ĐẦU GENERATE: {total} câu hỏi")

    processed = 0
    for idx, item in enumerate(eval_items[:total], start=1):
        sample_key = make_sample_key(item)
        if sample_key in done_keys:
            print(f"[{idx}/{total}] SKIP {sample_key}")
            continue

        question = item["question"]
        gold_ids = item.get("gold_ids", [])
        ground_truth = item.get("ground_truth", "")
        query_id = item.get("query_id")

        print(f"[{idx}/{total}] Đang xử lý: {question}")

        try:
            docs = retriever.invoke(question)
            contexts = [doc.page_content for doc in docs]
            retrieved_ids = [
                doc.metadata.get("sothutund")
                for doc in docs
                if isinstance(doc.metadata, dict) and doc.metadata.get("sothutund") is not None
            ]

            prompt = build_prompt(question, contexts)
            ans = generator_llm.invoke(prompt)
            answer_text = ans.content if hasattr(ans, "content") else str(ans)

            retrieval_metrics = compute_retrieval_metrics(gold_ids, retrieved_ids)
            out = {
                "sample_key": sample_key,
                "query_id": query_id,
                "question": question,
                "gold_ids": gold_ids,
                "ground_truth": ground_truth,
                "retrieved_ids": retrieved_ids,
                "contexts": contexts,
                "answer": answer_text,
                **retrieval_metrics,
            }
            append_jsonl(predictions_file, out)
            processed += 1

        except Exception as e:
            out = {
                "sample_key": sample_key,
                "query_id": query_id,
                "question": question,
                "gold_ids": gold_ids,
                "ground_truth": ground_truth,
                "retrieved_ids": [],
                "contexts": [],
                "answer": f"Lỗi hệ thống khi generate: {e}",
                "first_relevant_rank": None,
                "hit_at_k": 0,
                "recall_at_k": 0.0 if gold_ids else None,
                "mrr": 0.0,
                "generate_error": str(e),
            }
            append_jsonl(predictions_file, out)
            processed += 1
            print(f"   [!] Lỗi generate: {e}")

    print(f"\nĐã ghi {processed} mẫu mới vào {predictions_file}")


# =========================
# 5. JUDGE ONLY
# =========================
def judge_only(predictions_file: str, scores_file: str, limit: Optional[int] = None) -> None:
    if not ragas_llm or not ragas_emb:
        raise ValueError("Thiếu OPENAI_API_KEY hoặc chưa khởi tạo được RAGAS judge.")

    pred_items = load_jsonl(predictions_file)
    if not pred_items:
        raise FileNotFoundError(f"Không có predictions để chấm trong {predictions_file}")

    scored_items = load_jsonl(scores_file)
    scored_keys = {str(x.get("sample_key")) for x in scored_items if x.get("sample_key")}

    pending = [x for x in pred_items if str(x.get("sample_key")) not in scored_keys]
    if limit is not None:
        pending = pending[:limit]

    print(f"\nBẮT ĐẦU CHẤM: {len(pending)} mẫu")

    metrics = [
        ContextPrecision(llm=ragas_llm),
        ContextRecall(llm=ragas_llm),
        Faithfulness(llm=ragas_llm),
        RelevancyMetric(llm=ragas_llm, embeddings=ragas_emb),
    ]
    safe_config = RunConfig(max_workers=2, max_retries=5)

    for idx, item in enumerate(pending, start=1):
        print(f"[{idx}/{len(pending)}] Chấm: {item.get('question', '')}")
        sample_key = item.get("sample_key")
        out = dict(item)

        try:
            dataset = build_single_sample_dataset(item)
            result = evaluate(
                dataset=dataset,
                metrics=metrics,
                run_config=safe_config,
                raise_exceptions=False,
            )
            df = result.to_pandas()
            row = df.iloc[0].to_dict() if len(df) else {}

            out.update(
                {
                    "context_precision": row.get("context_precision"),
                    "context_recall": row.get("context_recall"),
                    "faithfulness": row.get("faithfulness"),
                    "answer_relevancy": row.get("answer_relevancy", row.get("response_relevancy")),
                }
            )

        except Exception as e:
            out.update(
                {
                    "context_precision": None,
                    "context_recall": None,
                    "faithfulness": None,
                    "answer_relevancy": None,
                    "judge_error": str(e),
                }
            )
            print(f"   [!] Lỗi judge: {e}")

        append_jsonl(scores_file, out)

    print(f"\nĐã ghi kết quả chấm vào {scores_file}")


# =========================
# 6. BUILD REPORT
# =========================
def build_report(scores_file: str, report_csv: str, summary_json: str) -> None:
    score_items = load_jsonl(scores_file)
    if not score_items:
        raise FileNotFoundError(f"Không có dữ liệu chấm trong {scores_file}")

    df = pd.DataFrame(score_items)
    df.to_csv(report_csv, index=False, encoding="utf-8-sig")

    numeric_cols = [
        "context_precision",
        "context_recall",
        "faithfulness",
        "answer_relevancy",
        "hit_at_k",
        "recall_at_k",
        "mrr",
    ]

    summary: Dict[str, Any] = {
        "num_rows": int(len(df)),
    }
    for col in numeric_cols:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            summary[col] = None if series.dropna().empty else float(series.mean())

    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\nKẾT QUẢ ĐÁNH GIÁ TỔNG QUAN")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nĐã xuất CSV: {report_csv}")
    print(f"Đã xuất summary: {summary_json}")


# =========================
# 7. MAIN
# =========================
def main() -> None:
    parser = argparse.ArgumentParser(description="Đánh giá RAG có hỗ trợ resume")
    parser.add_argument("--mode", choices=["generate_only", "judge_only", "build_report", "full"], default="full")
    parser.add_argument("--eval-file", default="danh_gia_rag.jsonl")
    parser.add_argument("--predictions-file", default="danh_gia_rag/rag_predictions.jsonl")
    parser.add_argument("--scores-file", default="danh_gia_rag/rag_scores.jsonl")
    parser.add_argument("--report-csv", default="danh_gia_rag/rag_evaluation_report.csv")
    parser.add_argument("--summary-json", default="danh_gia_rag/rag_evaluation_summary.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if args.mode == "generate_only":
        generate_only(args.eval_file, args.predictions_file, args.limit)
    elif args.mode == "judge_only":
        judge_only(args.predictions_file, args.scores_file, args.limit)
    elif args.mode == "build_report":
        build_report(args.scores_file, args.report_csv, args.summary_json)
    elif args.mode == "full":
        generate_only(args.eval_file, args.predictions_file, args.limit)
        judge_only(args.predictions_file, args.scores_file, args.limit)
        build_report(args.scores_file, args.report_csv, args.summary_json)


if __name__ == "__main__":
    main()
