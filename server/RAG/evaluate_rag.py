import os
import json
import pandas as pd
from dotenv import load_dotenv

from datasets import Dataset
from ragas import evaluate
from ragas.run_config import RunConfig

from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextRecall,
    ContextPrecision,
)

from supabase import create_client
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from openai import OpenAI
from ragas.llms import llm_factory
from ragas.embeddings import embedding_factory

# 1. CẤU HÌNH MÔI TRƯỜNG & KẾT NỐI
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("CẢNH BÁO: Chưa tìm thấy OPENAI_API_KEY trong file .env!")

print("\nĐang khởi tạo Supabase và Load Model E5 (Mất vài giây)...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")

# 2. RETRIEVER ĐỂ TÌM KIẾM TỪ SUPABASE
class LegalSupabaseRetriever(BaseRetriever):
    match_threshold: float = 0.45
    match_count: int = 5 

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        query_vector = embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        rpc_res = supabase.rpc(
            "match_legal_docs_v2",
            {
                "vector_truy_van": query_vector,
                "van_ban_truy_van": query,
                "nguong_khop": self.match_threshold,
                "so_luong_ket_qua": self.match_count,
            },
        ).execute()

        docs = []
        for hit in (rpc_res.data or []):
            docs.append(Document(page_content=hit.get("noidung", "")))
        return docs

retriever = LegalSupabaseRetriever()

# THÍ SINH: Qwen 2.5
generator_llm = ChatOllama(model="qwen2.5:7b", temperature=0.0)

# GIÁM KHẢO: OpenAI GPT-4o-mini
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Dùng llm_factory và embedding_factory chuẩn
ragas_llm = llm_factory('gpt-4o-mini', client=openai_client)
ragas_emb = embedding_factory('openai', model='text-embedding-3-small', client=openai_client)

# 4. CHẠY ĐÁNH GIÁ VÀ XUẤT REPORT
def run_evaluation():
    questions = []
    ground_truths = []
    contexts_list = []
    answers = []

    print("\nĐang nạp bộ đề thi eval.jsonl...")
    try:
        with open("eval_set_generated_strict.jsonl", "r", encoding="utf-8-sig") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    questions.append(item["question"])
                    ground_truths.append(item["ground_truth"])
    except Exception as e:
        print(f"LỖI LOAD FILE eval.jsonl: {e}")
        return

    print(f"\nBẮT ĐẦU GIẢI ĐỀ BẰNG QWEN 2.5 LOCAL ({len(questions)} câu hỏi)...")
    for idx, q in enumerate(questions):
        print(f"[{idx+1}/{len(questions)}] Đang xử lý: {q}")
        
        docs = retriever.invoke(q)
        context_texts = [doc.page_content for doc in docs]
        contexts_list.append(context_texts)
        
        joined_contexts = "\n".join(context_texts)
        prompt = f"Dựa vào luật sau:\n{joined_contexts}\n\nHãy trả lời: {q}"
        
        try:
            ans = generator_llm.invoke(prompt)
            answers.append(ans.content)
        except Exception as e:
            print(f"   [!] Lỗi Ollama: {e}")
            answers.append("Lỗi AI: Không thể trả lời")

    # Đóng gói dữ liệu
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths
    }
    dataset = Dataset.from_dict(data)

    print("\n>> GIÁM KHẢO OPENAI BẮT ĐẦU CHẤM ĐIỂM...")
    safe_config = RunConfig(max_workers=2, max_retries=5)

    result = evaluate(
        dataset=dataset,
        metrics=[
            ContextPrecision(llm=ragas_llm), 
            ContextRecall(llm=ragas_llm),    
            Faithfulness(llm=ragas_llm),      
            AnswerRelevancy(llm=ragas_llm, embeddings=ragas_emb),  
        ],
        run_config=safe_config,
        raise_exceptions=False 
    )

    print(" KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN (TRUNG BÌNH)")
    print(result)

    # Chuyển kết quả thành DataFrame
    df = result.to_pandas()
    
    print(" CHI TIẾT ĐIỂM SỐ TỪNG CÂU HỎI")
    if 'question' in df.columns:
        display_df = df[['question', 'context_precision', 'context_recall', 'faithfulness', 'answer_relevancy']]
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(display_df)

    # Xuất ra file CSV
    df.to_csv("rag_evaluation_report.csv", index=False, encoding="utf-8-sig")
    print("\nĐã xuất báo cáo chi tiết ra file: rag_evaluation_report.csv")

if __name__ == "__main__":
    run_evaluation()