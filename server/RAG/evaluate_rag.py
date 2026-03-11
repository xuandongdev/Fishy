# import os
# import json
# import pandas as pd
# from dotenv import load_dotenv

# from datasets import Dataset
# from ragas import evaluate
# from ragas.run_config import RunConfig  # Cấu hình chống quá tải API

# # Import các metric của Ragas theo chuẩn class mới
# from ragas.metrics import (
#     Faithfulness,
#     AnswerRelevancy,
#     ContextRecall,
#     ContextPrecision,
# )

# from supabase import create_client
# from sentence_transformers import SentenceTransformer
# from langchain_ollama import ChatOllama  # Thí sinh Local
# from langchain_google_genai import ChatGoogleGenerativeAI # Giám khảo Google
# from langchain_huggingface import HuggingFaceEmbeddings
# from langchain_core.retrievers import BaseRetriever
# from langchain_core.documents import Document

# # ==========================================
# # 1. CẤU HÌNH MÔI TRƯỜNG & KẾT NỐI
# # ==========================================
# load_dotenv()
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# if not os.getenv("GEMINI_API_KEY"):
#     print("⚠️ CẢNH BÁO: Chưa tìm thấy GEMINI_API_KEY trong file .env!")

# print(">> Đang khởi tạo Supabase và Load Model E5 (Mất vài giây)...")
# supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")

# # ==========================================
# # 2. RETRIEVER ĐỂ TÌM KIẾM TỪ SUPABASE
# # ==========================================
# class LegalSupabaseRetriever(BaseRetriever):
#     match_threshold: float = 0.45
#     match_count: int = 5 

#     def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
#         query_vector = embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
#         rpc_res = supabase.rpc(
#             "match_legal_docs_v3",
#             {
#                 "query_embedding": query_vector,
#                 "query_text": query,
#                 "match_threshold": self.match_threshold,
#                 "match_count": self.match_count,
#             },
#         ).execute()

#         docs = []
#         for hit in (rpc_res.data or []):
#             docs.append(Document(page_content=hit.get("noidung", "")))
#         return docs

# retriever = LegalSupabaseRetriever()

# # ==========================================
# # 3. KHỞI TẠO CÁC MÔ HÌNH AI
# # ==========================================
# # THÍ SINH (Local): Chạy Qwen 2.5 bằng Ollama (Miễn phí, bung hết tốc độ CPU)
# generator_llm = ChatOllama(model="qwen2.5:7b", temperature=0.0)

# # GIÁM KHẢO (Cloud): Dùng Gemini 1.5 Pro (Thông minh, miễn phí)
# judge_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0) 

# # EMBEDDING: Dùng E5 cục bộ để đồng nhất với database
# judge_embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")

# # ==========================================
# # 4. CHẠY ĐÁNH GIÁ VÀ XUẤT REPORT
# # ==========================================
# def run_evaluation():
#     questions = []
#     ground_truths = []
#     contexts_list = []
#     answers = []

#     print(">> Đang nạp bộ đề thi eval.jsonl...")
#     try:
#         with open("eval.jsonl", "r", encoding="utf-8") as f:
#             for line in f:
#                 if line.strip():
#                     item = json.loads(line)
#                     questions.append(item["question"])
#                     ground_truths.append(item["ground_truth"])
#     except FileNotFoundError:
#         print("LỖI: Không tìm thấy file eval.jsonl. Vui lòng tạo file này trước!")
#         return

#     print(f">> BẮT ĐẦU GIẢI ĐỀ BẰNG QWEN 2.5 LOCAL ({len(questions)} câu hỏi)...")
#     for idx, q in enumerate(questions):
#         print(f"[{idx+1}/{len(questions)}] Đang xử lý: {q}")
        
#         # A. Tìm luật từ Supabase
#         docs = retriever.invoke(q)
#         context_texts = [doc.page_content for doc in docs]
#         contexts_list.append(context_texts)
        
#         # B. Ép Thí sinh Local (Qwen 2.5) trả lời
#         joined_contexts = "\n".join(context_texts)
#         prompt = f"Dựa vào luật sau:\n{joined_contexts}\n\nHãy trả lời: {q}"
        
#         try:
#             ans = generator_llm.invoke(prompt)
#             answers.append(ans.content)
#         except Exception as e:
#             print(f"   [!] Lỗi Ollama: {e}")
#             answers.append("Lỗi AI: Không thể trả lời")

#     # Đóng gói dữ liệu thành Dataset
#     data = {
#         "question": questions,
#         "answer": answers,
#         "contexts": contexts_list,
#         "ground_truth": ground_truths
#     }
#     dataset = Dataset.from_dict(data)

#     print("\n>> GIÁM KHẢO GEMINI BẮT ĐẦU CHẤM ĐIỂM...")
#     print("   (Đã kích hoạt chế độ chống nghẽn API. Sẽ mất khoảng 5-10 phút, vui lòng treo máy chờ...)")
    
#     # Cấu hình ép Ragas chạy 1 luồng duy nhất để né lỗi 429
#     safe_config = RunConfig(
#         max_workers=1,  # Chỉ chạy 1 request/lần
#         max_retries=10  # Thử lại tối đa 10 lần nếu mạng chập chờn
#     )

#     # Bắt đầu chấm điểm
#     result = evaluate(
#         dataset=dataset,
#         metrics=[
#             ContextPrecision(), 
#             ContextRecall(),    
#             Faithfulness(),      
#             AnswerRelevancy(),  
#         ],
#         llm=judge_llm,
#         embeddings=judge_embeddings,
#         run_config=safe_config, # Gắn cấu hình an toàn vào đây
#         raise_exceptions=False 
#     )

#     print("\n==================================")
#     print(" KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN")
#     print("==================================")
#     print(result)

#     # Xuất ra file Excel/CSV
#     df = result.to_pandas()
#     df.to_csv("rag_evaluation_report.csv", index=False, encoding="utf-8-sig")
#     print("\n>> Đã xuất báo cáo chi tiết ra file: rag_evaluation_report.csv")

# if __name__ == "__main__":
#     run_evaluation()


# 2


# import os
# import json
# import pandas as pd
# from dotenv import load_dotenv

# from datasets import Dataset
# from ragas import evaluate
# from ragas.run_config import RunConfig

# # Import các metric của Ragas
# from ragas.metrics import (
#     Faithfulness,
#     AnswerRelevancy,
#     ContextRecall,
#     ContextPrecision,
# )

# from supabase import create_client
# from sentence_transformers import SentenceTransformer
# from langchain_ollama import ChatOllama
# from langchain_openai import ChatOpenAI  # Dùng ChatOpenAI để gọi API OpenRouter
# from langchain_huggingface import HuggingFaceEmbeddings
# from langchain_core.retrievers import BaseRetriever
# from langchain_core.documents import Document

# # ==========================================
# # 1. CẤU HÌNH MÔI TRƯỜNG & KẾT NỐI
# # ==========================================
# load_dotenv()
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# if not os.getenv("OPENROUTER_API_KEY"):
#     print("⚠️ CẢNH BÁO: Chưa tìm thấy OPENROUTER_API_KEY trong file .env!")

# print(">> Đang khởi tạo Supabase và Load Model E5 (Mất vài giây)...")
# supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")

# # ==========================================
# # 2. RETRIEVER ĐỂ TÌM KIẾM TỪ SUPABASE
# # ==========================================
# class LegalSupabaseRetriever(BaseRetriever):
#     match_threshold: float = 0.45
#     match_count: int = 5 

#     def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
#         query_vector = embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
#         rpc_res = supabase.rpc(
#             "match_legal_docs_v3",
#             {
#                 "query_embedding": query_vector,
#                 "query_text": query,
#                 "match_threshold": self.match_threshold,
#                 "match_count": self.match_count,
#             },
#         ).execute()

#         docs = []
#         for hit in (rpc_res.data or []):
#             docs.append(Document(page_content=hit.get("noidung", "")))
#         return docs

# retriever = LegalSupabaseRetriever()

# # ==========================================
# # 3. KHỞI TẠO CÁC MÔ HÌNH AI (OLLAMA + OPENROUTER)
# # ==========================================
# # THÍ SINH: Qwen 2.5 chạy Local (Tốc độ bàn thờ, bung sức mạnh chip Ryzen 7)
# generator_llm = ChatOllama(model="qwen2.5:7b", temperature=0.0)

# # GIÁM KHẢO: Dùng OpenRouter API. 
# # LangChain OpenAI tương thích hoàn toàn với OpenRouter, chỉ cần đổi base_url.
# judge_llm = ChatOpenAI(
#     openai_api_key=os.getenv("OPENROUTER_API_KEY"),
#     openai_api_base="https://openrouter.ai/api/v1",
#     model_name="google/gemini-2.0-flash:free", # Gọi bản Flash miễn phí siêu tốc của Google qua OpenRouter
#     temperature=0.0,
#     max_retries=3,
#     timeout=120.0 # Tăng thời gian chờ lên 120s để triệt tiêu lỗi TimeoutError
# )

# # EMBEDDING: Dùng E5 cục bộ
# judge_embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")

# # ==========================================
# # 4. CHẠY ĐÁNH GIÁ VÀ XUẤT REPORT
# # ==========================================
# def run_evaluation():
#     questions = []
#     ground_truths = []
#     contexts_list = []
#     answers = []

#     print(">> Đang nạp bộ đề thi eval.jsonl...")
#     try:
#         with open("eval.jsonl", "r", encoding="utf-8") as f:
#             for line in f:
#                 if line.strip():
#                     item = json.loads(line)
#                     questions.append(item["question"])
#                     ground_truths.append(item["ground_truth"])
#     except FileNotFoundError:
#         print("LỖI: Không tìm thấy file eval.jsonl!")
#         return

#     print(f">> BẮT ĐẦU GIẢI ĐỀ BẰNG QWEN 2.5 LOCAL ({len(questions)} câu hỏi)...")
#     for idx, q in enumerate(questions):
#         print(f"[{idx+1}/{len(questions)}] Đang xử lý: {q}")
        
#         # A. Tìm luật từ Supabase
#         docs = retriever.invoke(q)
#         context_texts = [doc.page_content for doc in docs]
#         contexts_list.append(context_texts)
        
#         # B. Thí sinh Local trả lời (Không cần sleep vì chạy offline trên máy bạn)
#         joined_contexts = "\n".join(context_texts)
#         prompt = f"Dựa vào luật sau:\n{joined_contexts}\n\nHãy trả lời: {q}"
        
#         try:
#             ans = generator_llm.invoke(prompt)
#             answers.append(ans.content)
#         except Exception as e:
#             print(f"   [!] Lỗi Ollama: {e}")
#             answers.append("Lỗi AI: Không thể trả lời")

#     # Đóng gói dữ liệu
#     data = {
#         "question": questions,
#         "answer": answers,
#         "contexts": contexts_list,
#         "ground_truth": ground_truths
#     }
#     dataset = Dataset.from_dict(data)

#     print("\n>> GIÁM KHẢO OPENROUTER BẮT ĐẦU CHẤM ĐIỂM...")
    
#     # Cấu hình luồng chạy (Tăng tốc độ lên một chút so với lúc nãy vì OpenRouter mạnh hơn)
#     safe_config = RunConfig(
#         max_workers=2, 
#         max_retries=5
#     )

#     # Bắt đầu chấm điểm
#     result = evaluate(
#         dataset=dataset,
#         metrics=[
#             ContextPrecision(), 
#             ContextRecall(),    
#             Faithfulness(),      
#             AnswerRelevancy(),  
#         ],
#         llm=judge_llm,
#         embeddings=judge_embeddings,
#         run_config=safe_config,
#         raise_exceptions=False 
#     )

#     print("\n==================================")
#     print(" KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN")
#     print("==================================")
#     print(result)

#     # Xuất ra file CSV
#     df = result.to_pandas()
#     df.to_csv("rag_evaluation_report.csv", index=False, encoding="utf-8-sig")
#     print("\n>> Đã xuất báo cáo chi tiết ra file: rag_evaluation_report.csv")

# if __name__ == "__main__":
#     run_evaluation()


# 3
import os
import json
import pandas as pd
from dotenv import load_dotenv

from datasets import Dataset
from ragas import evaluate
from ragas.run_config import RunConfig

# Import các metric của Ragas theo chuẩn class mới
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextRecall,
    ContextPrecision,
)

from supabase import create_client
from sentence_transformers import SentenceTransformer
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI  # Dùng ChatOpenAI để gọi thẳng API của OpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

# ==========================================
# 1. CẤU HÌNH MÔI TRƯỜNG & KẾT NỐI
# ==========================================
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Kiểm tra Key của OpenAI
if not os.getenv("OPENAI_API_KEY"):
    print("⚠️ CẢNH BÁO: Chưa tìm thấy OPENAI_API_KEY trong file .env!")

print(">> Đang khởi tạo Supabase và Load Model E5 (Mất vài giây)...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")

# ==========================================
# 2. RETRIEVER ĐỂ TÌM KIẾM TỪ SUPABASE
# ==========================================
class LegalSupabaseRetriever(BaseRetriever):
    match_threshold: float = 0.45
    match_count: int = 5 

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        query_vector = embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        rpc_res = supabase.rpc(
            "match_legal_docs_v4",
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

# ==========================================
# 3. KHỞI TẠO CÁC MÔ HÌNH AI (OLLAMA + OPENAI)
# ==========================================
# THÍ SINH: Qwen 2.5 chạy Local (Tốc độ bàn thờ, bung sức mạnh chip Ryzen 7)
generator_llm = ChatOllama(model="qwen2.5:7b", temperature=0.0)

# GIÁM KHẢO: Dùng thẳng OpenAI API (Yêu cầu tài khoản có credit/đã add thẻ)
judge_llm = ChatOpenAI(
    model_name="gpt-4o-mini", # Model nhanh, rẻ và cực kỳ thông minh của OpenAI
    temperature=0.0,
    max_retries=3,
    timeout=120.0 
)

# EMBEDDING: Dùng E5 cục bộ
judge_embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")

# ==========================================
# 4. CHẠY ĐÁNH GIÁ VÀ XUẤT REPORT
# ==========================================
def run_evaluation():
    questions = []
    ground_truths = []
    contexts_list = []
    answers = []

    print(">> Đang nạp bộ đề thi eval.jsonl...")
    try:
        with open("eval.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    questions.append(item["question"])
                    ground_truths.append(item["ground_truth"])
    except FileNotFoundError:
        print("LỖI: Không tìm thấy file eval.jsonl!")
        return

    print(f">> BẮT ĐẦU GIẢI ĐỀ BẰNG QWEN 2.5 LOCAL ({len(questions)} câu hỏi)...")
    for idx, q in enumerate(questions):
        print(f"[{idx+1}/{len(questions)}] Đang xử lý: {q}")
        
        # A. Tìm luật từ Supabase
        docs = retriever.invoke(q)
        context_texts = [doc.page_content for doc in docs]
        contexts_list.append(context_texts)
        
        # B. Thí sinh Local trả lời (Không cần sleep vì chạy offline trên máy bạn)
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
    
    # Cấu hình luồng chạy (Để 2 workers giúp OpenAI chấm nhanh hơn)
    safe_config = RunConfig(
        max_workers=2, 
        max_retries=5
    )

    # Bắt đầu chấm điểm
    result = evaluate(
        dataset=dataset,
        metrics=[
            ContextPrecision(), 
            ContextRecall(),    
            Faithfulness(),      
            AnswerRelevancy(),  
        ],
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=safe_config,
        raise_exceptions=False 
    )

    print("\n===============================================")
    print(" KẾT QUẢ ĐÁNH GIÁ TỔNG QUAN (TRUNG BÌNH)")
    print("===============================================")
    print(result)

    # Chuyển kết quả thành DataFrame
    df = result.to_pandas()
    
    # ---------------------------------------------------------
    # IN ĐIỂM TỪNG CÂU RA TERMINAL
    print("\n===============================================")
    print(" CHI TIẾT ĐIỂM SỐ TỪNG CÂU HỎI")
    print("===============================================")
    # Lọc ra các cột điểm để in cho dễ nhìn
    df = df.reset_index()
    display_df = df[['question', 'context_precision', 'context_recall', 'faithfulness', 'answer_relevancy']]
    
    # Cấu hình Pandas để không bị ẩn text khi in ra Terminal
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(display_df)
    # ---------------------------------------------------------

    # Xuất ra file CSV
    df.to_csv("rag_evaluation_report.csv", index=False, encoding="utf-8-sig")
    print("\n>> Đã xuất báo cáo chi tiết ra file: rag_evaluation_report.csv")

if __name__ == "__main__":
    run_evaluation()