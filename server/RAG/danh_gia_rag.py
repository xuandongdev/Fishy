from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


SUPABASE_URL: Optional[str] = None
SUPABASE_KEY: Optional[str] = None
OPENAI_API_KEY: Optional[str] = None
OLLAMA_MODEL = "qwen2.5:7b"
GENERATOR_TEMPERATURE = 0.2

MATCH_THRESHOLD = 0.60
MATCH_COUNT = 5
OUTPUT_DIR = "danh_gia_rag/danh_gia_060"

OPENAI_JUDGE_MODEL = "gpt-4o-mini"
JUDGE_MAX_TOKENS = 4096
HF_EMBED_MODEL = "intfloat/multilingual-e5-large"
TRUSTED_RAG_EVAL_URL: Optional[str] = None

Dataset = None
evaluate = None
RunConfig = None
Faithfulness = None
ContextRecall = None
ContextPrecision = None
RelevancyMetric = None
retriever = None
generator_chain = None
ragas_llm = None
ragas_emb = None
_RUNTIME_INITIALIZED = False


VEHICLE_TYPES = {"o_to", "xe_may", "xe_dap", "di_bo", "khac"}


def initialize_runtime() -> None:
    global SUPABASE_URL
    global SUPABASE_KEY
    global OPENAI_API_KEY
    global OLLAMA_MODEL
    global GENERATOR_TEMPERATURE
    global MATCH_THRESHOLD
    global MATCH_COUNT
    global OUTPUT_DIR
    global OPENAI_JUDGE_MODEL
    global JUDGE_MAX_TOKENS
    global HF_EMBED_MODEL
    global TRUSTED_RAG_EVAL_URL
    global Dataset
    global evaluate
    global RunConfig
    global Faithfulness
    global ContextRecall
    global ContextPrecision
    global RelevancyMetric
    global retriever
    global generator_chain
    global ragas_llm
    global ragas_emb
    global _RUNTIME_INITIALIZED

    if _RUNTIME_INITIALIZED:
        return

    from dotenv import load_dotenv
    from datasets import Dataset as _Dataset
    from ragas import evaluate as _evaluate
    from ragas.run_config import RunConfig as _RunConfig
    from ragas.metrics import Faithfulness as _Faithfulness
    from ragas.metrics import ContextRecall as _ContextRecall
    from ragas.metrics import ContextPrecision as _ContextPrecision
    try:
        from ragas.metrics import ResponseRelevancy as _RelevancyMetric
    except Exception:
        from ragas.metrics import AnswerRelevancy as _RelevancyMetric
    from supabase import create_client
    from sentence_transformers import SentenceTransformer
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_ollama import ChatOllama
    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings.base import BaseRagasEmbeddings

    load_dotenv()

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OLLAMA_MODEL = "qwen2.5:7b"
    GENERATOR_TEMPERATURE = 0.2
    OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini")
    HF_EMBED_MODEL = os.getenv("HF_EMBED_MODEL", "intfloat/multilingual-e5-large")
    TRUSTED_RAG_EVAL_URL = os.getenv("TRUSTED_RAG_EVAL_URL", "").strip() or None

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Thieu SUPABASE_URL hoac SUPABASE_SERVICE_ROLE_KEY trong file .env")

    if not OPENAI_API_KEY:
        print("CANH BAO: Chua tim thay OPENAI_API_KEY trong .env. Buoc judge co the khong chay duoc, nhung generate bang Ollama van co the chay.")

    print("\nDang khoi tao Supabase va model embedding E5...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    def load_embedding_model(model_name: str):
        try:
            return SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            return SentenceTransformer(model_name)

    embedding_model = load_embedding_model(HF_EMBED_MODEL)

    class E5RagasEmbeddings(BaseRagasEmbeddings):
        def __init__(self, model) -> None:
            super().__init__()
            self.model = model

        def embed_query(self, text: str) -> List[float]:
            return self.embed_documents([text])[0]

        def embed_documents(self, texts: List[str]) -> List[List[float]]:
            prefixed_texts = [f"query: {(text or '').strip()}" for text in texts]
            embeddings = self.model.encode(
                prefixed_texts,
                normalize_embeddings=True,
            )
            return embeddings.tolist()

        async def aembed_query(self, text: str) -> List[float]:
            return (await self.aembed_documents([text]))[0]

        async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
            return await asyncio.to_thread(self.embed_documents, texts)

    class LegalSupabaseRetriever(BaseRetriever):
        match_threshold: float = MATCH_THRESHOLD
        match_count: int = MATCH_COUNT

        def detect_vehicle_type(self, query: str) -> str:
            q = (query or "").strip().lower()

            if re.search(
                r"\b(ô tô|oto|o to|xe hơi|xe hoi|xe con|xe tải|xe tai|xe khách|xe khach|xe bán tải|xe ban tai|đầu kéo|dau keo|container|rơ moóc|ro mooc|sơ mi rơ moóc|so mi ro mooc)\b",
                q,
            ):
                return "o_to"

            if re.search(r"\b(xe máy|xe may|mô tô|mo to|moto|motor|xe gắn máy|xe gan may)\b", q):
                return "xe_may"

            if re.search(r"\b(xe đạp|xe dap|xe đạp điện|xe dap dien|xe thô sơ|xe tho so)\b", q):
                return "xe_dap"

            if re.search(r"\b(đi bộ|di bo|người đi bộ|nguoi di bo|bộ hành|bo hanh)\b", q):
                return "di_bo"

            return "khac"

        def extract_km(self, query: str) -> Optional[float]:
            pattern = (
                r"(\d+(?:[\.,]\d+)?)\s*(?:km/h|km|kmh|cây số|cay so|cây|cay)"
                r"|(?:quá|qua|lố|lo|chạy|chay|mức|muc|tốc độ|toc do)\s*(\d+(?:[\.,]\d+)?)"
            )
            match = re.search(pattern, query, re.IGNORECASE)
            if not match:
                return None

            raw_value = match.group(1) or match.group(2)
            if not raw_value:
                return None

            try:
                return float(raw_value.replace(",", "."))
            except ValueError:
                return None

        def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
            query_vector = embedding_model.encode(
                "query: " + query,
                normalize_embeddings=True,
            ).tolist()
            query_km = self.extract_km(query)
            vehicle_type = self.detect_vehicle_type(query)

            rpc_res = supabase.rpc(
                "match_legal_docs_v2",
                {
                    "vector_truy_van": query_vector,
                    "van_ban_truy_van": query,
                    "nguong_khop": self.match_threshold,
                    "so_luong_ket_qua": self.match_count,
                    "so_km_truy_van": query_km,
                    "p_loai_phuong_tien_truy_van": vehicle_type,
                },
            ).execute()

            docs: List[Document] = []
            for hit in (rpc_res.data or []):
                docs.append(
                    Document(
                        page_content=hit.get("noidung", ""),
                        metadata={
                            "sothutund": hit.get("sothutund"),
                            "sohieu": hit.get("sohieu"),
                            "path": hit.get("duong_dan_phan_cap"),
                            "vehicle_type": hit.get("loai_phuong_tien") if str(hit.get("loai_phuong_tien") or "").strip().lower() in VEHICLE_TYPES else None,
                        },
                    )
                )
            return docs

    generator_llm = ChatOllama(
        model=OLLAMA_MODEL,
        temperature=GENERATOR_TEMPERATURE,
    )
    generator_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Ban la Tro ly Luat Giao thong Fishy. Hay tra loi dua tren du lieu phap luat duoc cung cap.\n"
                "Neu cau hoi co nhac ro loai phuong tien (o to, xe may, xe dap, di bo), hay uu tien doi chieu dung nhom do.\n"
                "Khi co so lieu cu the nhu toc do, hay doi chieu chinh xac muc phat.\n\n"
                "DU LIEU LUAT:\n{context}",
            ),
            ("human", "{question}"),
        ]
    )

    judge_base_llm = (
        ChatOpenAI(
            model=OPENAI_JUDGE_MODEL,
            api_key=OPENAI_API_KEY,
            temperature=0,
            max_tokens=JUDGE_MAX_TOKENS,
        )
        if OPENAI_API_KEY
        else None
    )

    Dataset = _Dataset
    evaluate = _evaluate
    RunConfig = _RunConfig
    Faithfulness = _Faithfulness
    ContextRecall = _ContextRecall
    ContextPrecision = _ContextPrecision
    RelevancyMetric = _RelevancyMetric
    retriever = LegalSupabaseRetriever()
    generator_chain = (generator_prompt | generator_llm | StrOutputParser()) if generator_llm else None
    ragas_llm = LangchainLLMWrapper(judge_base_llm) if judge_base_llm else None
    ragas_emb = E5RagasEmbeddings(embedding_model)
    _RUNTIME_INITIALIZED = True


def normalize_question(q: str) -> str:
    return " ".join((q or "").strip().split())


def make_sample_key(item: Dict[str, Any]) -> str:
    return str(item.get("query_id") or normalize_question(item.get("question", "")))


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8-sig") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL khong hop le o {path}, dong {line_no}: {exc.msg}") from exc
    return items


def dedupe_latest_by_sample_key(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    passthrough: List[Dict[str, Any]] = []
    for item in items:
        key = str(item.get("sample_key") or "").strip()
        if not key:
            passthrough.append(item)
            continue
        latest[key] = item
    return passthrough + list(latest.values())


def load_completed_keys(path: str, error_field: Optional[str] = None, retry_errors: bool = False) -> set[str]:
    items = dedupe_latest_by_sample_key(load_jsonl(path))
    done_keys: set[str] = set()
    for item in items:
        key = str(item.get("sample_key") or "").strip()
        if not key:
            continue
        if retry_errors and error_field and item.get(error_field):
            continue
        done_keys.add(key)
    return done_keys


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def append_jsonl(path: str, item: Dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def collect_fieldnames(items: List[Dict[str, Any]]) -> List[str]:
    fieldnames: List[str] = []
    seen = set()
    for item in items:
        for key in item.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    return fieldnames


def write_report_csv(path: str, items: List[Dict[str, Any]]) -> None:
    ensure_parent_dir(path)
    fieldnames = collect_fieldnames(items)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow({key: csv_cell(item.get(key)) for key in fieldnames})


def format_docs(docs: List[Any]) -> str:
    if not docs:
        return "Khong co du lieu luat duoc truy xuat."

    return "\n\n".join(
        [
            f"--- CAN CU: {doc.metadata.get('path', 'N/A')} ---\n{doc.page_content}"
            for doc in docs
        ]
    )


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


def build_single_sample_dataset(item: Dict[str, Any]):
    initialize_runtime()
    data = {
        "question": [item.get("question", "")],
        "answer": [item.get("answer", "")],
        "contexts": [item.get("contexts", [])],
        "ground_truth": [item.get("ground_truth", "")],
        "user_input": [item.get("question", "")],
        "response": [item.get("answer", "")],
        "retrieved_contexts": [item.get("contexts", [])],
        "reference": [item.get("ground_truth", "")],
    }
    return Dataset.from_dict(data)


def call_trusted_rag_eval(question: str) -> Dict[str, Any]:
    initialize_runtime()
    if not TRUSTED_RAG_EVAL_URL:
        raise ValueError("Chua cau hinh TRUSTED_RAG_EVAL_URL de goi trusted_rag_app.")

    payload = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        TRUSTED_RAG_EVAL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"trusted_rag_app tra ve HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Khong ket noi duoc trusted_rag_app: {exc.reason}") from exc


def extract_eval_fields_from_api(response: Dict[str, Any]) -> Dict[str, Any]:
    evaluation = (response or {}).get("evaluation") or {}
    hits = evaluation.get("hits") or []
    retrieved_ids = [item.get("primary_id") for item in hits if item.get("primary_id") is not None]
    contexts = [(item.get("content") or "") for item in hits if item.get("content")]
    retrieved_paths = [
        item.get("label") or item.get("url")
        for item in hits
        if item.get("label") or item.get("url")
    ]
    timings = evaluation.get("timings") or {}
    return {
        "answer": (response or {}).get("answer", ""),
        "retrieved_ids": retrieved_ids,
        "contexts": contexts,
        "retrieved_paths": retrieved_paths,
        "detected_vehicle_type": evaluation.get("detected_vehicle_type"),
        "latency_ms": safe_float(timings.get("latency_ms")),
        "retrieval_time_ms": safe_float(timings.get("retrieval_time_ms")),
        "rerank_time_ms": safe_float(timings.get("rerank_time_ms")),
        "gen_time_ms": safe_float(timings.get("gen_time_ms")),
    }


def generate_only(eval_file: str, predictions_file: str, limit: Optional[int] = None) -> None:
    initialize_runtime()
    use_trusted_rag_api = bool(TRUSTED_RAG_EVAL_URL)
    if not use_trusted_rag_api and not generator_chain:
        raise ValueError("Chua khoi tao duoc generator Ollama. Hay chay `ollama run qwen2.5:7b` truoc khi goi danh_gia_rag.py.")

    eval_items = load_jsonl(eval_file)
    if not eval_items:
        raise FileNotFoundError(f"Khong doc duoc du lieu tu {eval_file}")

    done_keys = load_completed_keys(
        predictions_file,
        error_field="generate_error",
        retry_errors=os.getenv("RETRY_GENERATE_ERRORS", "0") == "1",
    )

    total = len(eval_items) if limit is None else min(len(eval_items), limit)
    print(f"\nBAT DAU GENERATE: {total} cau hoi")

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

        print(f"[{idx}/{total}] Dang xu ly: {question}")

        try:
            if use_trusted_rag_api:
                api_start = time.perf_counter()
                api_result = call_trusted_rag_eval(question)
                api_end = time.perf_counter()

                eval_result = extract_eval_fields_from_api(api_result)
                contexts = eval_result["contexts"]
                retrieved_ids = eval_result["retrieved_ids"]
                answer_text = eval_result["answer"]
                retrieved_paths = eval_result["retrieved_paths"]
                detected_vehicle_type = eval_result.get("detected_vehicle_type")

                latency_ms = eval_result.get("latency_ms")
                if latency_ms is None:
                    latency_ms = (api_end - api_start) * 1000
                retrieval_time_ms = eval_result.get("retrieval_time_ms")
                rerank_time_ms = eval_result.get("rerank_time_ms")
                gen_time_ms = eval_result.get("gen_time_ms")
            else:
                total_start = time.perf_counter()
                detected_vehicle_type = retriever.detect_vehicle_type(question)

                retrieval_start = time.perf_counter()
                docs = retriever.invoke(question)
                retrieval_end = time.perf_counter()

                rerank_start = retrieval_end
                rerank_end = rerank_start

                generation_start = time.perf_counter()
                answer_text = generator_chain.invoke(
                    {
                        "context": format_docs(docs),
                        "question": question,
                    }
                )
                generation_end = time.perf_counter()

                total_end = generation_end

                contexts = [doc.page_content for doc in docs]
                retrieved_ids = [
                    doc.metadata.get("sothutund")
                    for doc in docs
                    if isinstance(doc.metadata, dict) and doc.metadata.get("sothutund") is not None
                ]
                retrieved_paths = [
                    doc.metadata.get("path")
                    for doc in docs
                    if isinstance(doc.metadata, dict)
                ]

                retrieval_time_ms = (retrieval_end - retrieval_start) * 1000
                rerank_time_ms = (rerank_end - rerank_start) * 1000
                gen_time_ms = (generation_end - generation_start) * 1000
                latency_ms = (total_end - total_start) * 1000

            retrieval_metrics = compute_retrieval_metrics(gold_ids, retrieved_ids)
            out = {
                "sample_key": sample_key,
                "query_id": query_id,
                "question": question,
                "gold_ids": gold_ids,
                "ground_truth": ground_truth,
                "threshold": MATCH_THRESHOLD,
                "k": MATCH_COUNT,
                "detected_vehicle_type": detected_vehicle_type,
                "retrieved_ids": retrieved_ids,
                "contexts": contexts,
                "retrieved_paths": retrieved_paths,
                "answer": answer_text,
                "latency_ms": latency_ms,
                "retrieval_time_ms": retrieval_time_ms,
                "rerank_time_ms": rerank_time_ms,
                "gen_time_ms": gen_time_ms,
                **retrieval_metrics,
            }
            append_jsonl(predictions_file, out)
            processed += 1

        except Exception as exc:
            out = {
                "sample_key": sample_key,
                "query_id": query_id,
                "question": question,
                "gold_ids": gold_ids,
                "ground_truth": ground_truth,
                "threshold": MATCH_THRESHOLD,
                "k": MATCH_COUNT,
                "detected_vehicle_type": None,
                "retrieved_ids": [],
                "contexts": [],
                "answer": f"Loi he thong khi generate: {exc}",
                "latency_ms": None,
                "retrieval_time_ms": None,
                "rerank_time_ms": None,
                "gen_time_ms": None,
                "first_relevant_rank": None,
                "hit_at_k": 0,
                "recall_at_k": 0.0 if gold_ids else None,
                "mrr": 0.0,
                "generate_error": str(exc),
            }
            append_jsonl(predictions_file, out)
            processed += 1
            print(f"   [!] Loi generate: {exc}")

    print(f"\nDa ghi {processed} mau moi vao {predictions_file}")


def judge_only(predictions_file: str, scores_file: str, limit: Optional[int] = None) -> None:
    initialize_runtime()
    if not ragas_llm or not ragas_emb:
        raise ValueError("Thieu OPENAI_API_KEY hoac chua khoi tao duoc RAGAS judge.")

    pred_items = load_jsonl(predictions_file)
    if not pred_items:
        raise FileNotFoundError(f"Khong co predictions de cham trong {predictions_file}")

    scored_keys = load_completed_keys(
        scores_file,
        error_field="judge_error",
        retry_errors=os.getenv("RETRY_JUDGE_ERRORS", "0") == "1",
    )

    pending = [x for x in pred_items if str(x.get("sample_key")) not in scored_keys]
    if limit is not None:
        pending = pending[:limit]

    print(f"\nBAT DAU CHAM: {len(pending)} mau")

    metrics = [
        ContextPrecision(llm=ragas_llm),
        ContextRecall(llm=ragas_llm),
        Faithfulness(llm=ragas_llm),
        RelevancyMetric(llm=ragas_llm, embeddings=ragas_emb),
    ]
    safe_config = RunConfig(max_workers=2, max_retries=2)

    for idx, item in enumerate(pending, start=1):
        print(f"[{idx}/{len(pending)}] Cham: {item.get('question', '')}")
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

        except Exception as exc:
            out.update(
                {
                    "context_precision": None,
                    "context_recall": None,
                    "faithfulness": None,
                    "answer_relevancy": None,
                    "judge_error": str(exc),
                }
            )
            print(f"   [!] Loi judge: {exc}")

        append_jsonl(scores_file, out)

    print(f"\nDa ghi ket qua cham vao {scores_file}")


def build_report(scores_file: str, report_csv: str, summary_json: str) -> None:
    score_items = dedupe_latest_by_sample_key(load_jsonl(scores_file))
    if not score_items:
        raise FileNotFoundError(f"Khong co du lieu cham trong {scores_file}")

    write_report_csv(report_csv, score_items)

    numeric_cols = [
        "latency_ms",
        "retrieval_time_ms",
        "rerank_time_ms",
        "gen_time_ms",
        "context_precision",
        "context_recall",
        "faithfulness",
        "answer_relevancy",
        "hit_at_k",
        "recall_at_k",
        "mrr",
    ]

    summary: Dict[str, Any] = {
        "num_rows": len(score_items),
    }
    for col in numeric_cols:
        values = [safe_float(item.get(col)) for item in score_items]
        valid = [value for value in values if value is not None]
        if valid:
            summary[col] = sum(valid) / len(valid)

    ensure_parent_dir(summary_json)
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\nKET QUA DANH GIA TONG QUAN")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nDa xuat CSV: {report_csv}")
    print(f"Da xuat summary: {summary_json}")


def main() -> None:
    global MATCH_THRESHOLD
    global MATCH_COUNT
    global OUTPUT_DIR

    threshold_tag = f"{MATCH_THRESHOLD:.2f}".replace(".", "")
    default_run_tag = f"ollama_qwen25_7b_t{threshold_tag}_k{MATCH_COUNT}"

    parser = argparse.ArgumentParser(description="Danh gia RAG theo pipeline local/trusted_rag_app, co ho tro resume")
    parser.add_argument("--mode", choices=["generate_only", "judge_only", "build_report", "full"], default="full")
    parser.add_argument("--eval-file", default="danh_gia_rag.jsonl")
    parser.add_argument("--run-tag", default=default_run_tag)
    parser.add_argument("--predictions-file", default=None)
    parser.add_argument("--scores-file", default=None)
    parser.add_argument("--report-csv", default=None)
    parser.add_argument("--summary-json", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--retry-generate-errors", action="store_true")
    parser.add_argument("--retry-judge-errors", action="store_true")
    args = parser.parse_args()

    if args.retry_generate_errors:
        os.environ["RETRY_GENERATE_ERRORS"] = "1"
    if args.retry_judge_errors:
        os.environ["RETRY_JUDGE_ERRORS"] = "1"

    if not args.predictions_file:
        args.predictions_file = f"{OUTPUT_DIR}/rag_predictions_{args.run_tag}.jsonl"
    if not args.scores_file:
        args.scores_file = f"{OUTPUT_DIR}/rag_scores_{args.run_tag}.jsonl"
    if not args.report_csv:
        args.report_csv = f"{OUTPUT_DIR}/rag_evaluation_report_{args.run_tag}.csv"
    if not args.summary_json:
        args.summary_json = f"{OUTPUT_DIR}/rag_evaluation_summary_{args.run_tag}.json"

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
