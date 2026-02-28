import os
import json
import pandas as pd
from dotenv import load_dotenv

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_recall,
    context_precision,
)

from supabase import create_client
from sentence_transformers import SentenceTransformer
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

# 1. LOAD BIẾN MÔI TRƯỜNG
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Khởi tạo Supabase & Embedding Model
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")

# 2. ĐỊNH NGHĨA LẠI CUSTOM RETRIEVER ĐỂ TÁI SỬ DỤNG
class LegalSupabaseRetriever(BaseRetriever):
    match_threshold: float = 0.45
    match_count: int = 5 # Đánh giá Top 5 kết quả

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        query_vector = embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        rpc_res = supabase.rpc(
            "match_legal_docs_v3",
            {
                "query_embedding": query_vector,
                "query_text": query,
                "match_threshold": self.match_threshold,
                "match_count": self.match_count,
            },
        ).execute()

        docs = []
        for hit in (rpc_res.data or []):
            docs.append(Document(page_content=hit.get("noidung", "")))
        return docs

retriever = LegalSupabaseRetriever()

# Khởi tạo mô hình Gemini sinh câu trả lời và làm Giám khảo
generator_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0)
judge_llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.0) 

def run_evaluation():
    questions = []
    ground_truths = []
    contexts_list = []
    answers = []

    print(">> Đang nạp bộ đề thi eval.jsonl...")
    with open("eval.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                questions.append(item["question"])
                ground_truths.append(item["ground_truth"])

    print(f">> Bắt đầu quá trình giải đề ({len(questions)} câu hỏi)...")
    for q in questions:
        print(f" - Đang truy xuất & trả lời: {q}")
        
        # A. Chạy khâu Retrieval (Tìm kiếm)
        docs = retriever.invoke(q)
        context_texts = [doc.page_content for doc in docs]
        contexts_list.append(context_texts)
        
        # B. Chạy khâu Generation (Tạo sinh)
        # Ép Gemini trả lời dựa đúng vào context_texts vừa tìm được
        joined_contexts = "\n".join(context_texts)
        prompt = f"Dựa vào luật sau:\n{joined_contexts}\n\nHãy trả lời: {q}"
        
        ans = generator_llm.invoke(prompt)
        answers.append(ans.content)

    # Đóng gói dữ liệu thành chuẩn HuggingFace Dataset cho Ragas
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths
    }
    dataset = Dataset.from_dict(data)

    print("\n>> Bắt đầu quá trình Giám khảo AI chấm điểm (Ragas)...")
    result = evaluate(
        dataset=dataset,
        metrics=[
            context_precision, 
            context_recall,    
            faithfulness,      
            answer_relevancy,  
        ],
        llm=judge_llm
    )

    print("\n=== KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN ===")
    print(result)

    # Xuất file CSV chi tiết để phân tích
    df = result.to_pandas()
    df.to_csv("rag_evaluation_report.csv", index=False, encoding="utf-8-sig")
    print("\n>> Đã lưu báo cáo chi tiết vào file: rag_evaluation_report.csv")

if __name__ == "__main__":
    run_evaluation()