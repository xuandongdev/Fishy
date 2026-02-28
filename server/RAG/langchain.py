import os
import time
import logging
import uuid
import json
import subprocess
import re
import threading
from typing import List, Any, Dict, Optional
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# --- Supabase & Embedding ---
from supabase import create_client
from sentence_transformers import SentenceTransformer

# --- LangChain Imports ---
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

# ======================================================
# 1. CẤU HÌNH HỆ THỐNG
# ======================================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PORT_NUMBER = 8000  # Server RAG chạy port 8000

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("LỖI: Chưa cấu hình SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY")
if not GEMINI_API_KEY:
    raise ValueError("LỖI: Chưa cấu hình GEMINI_API_KEY")

if not os.path.exists("logs"):
    os.makedirs("logs")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | %(message)s",
    handlers=[
        logging.FileHandler(f"logs/langchain_server_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("LANGCHAIN_SERVER")

# ======================================================
# 2. HÀM TỰ ĐỘNG CLOUDFLARE (Cập nhật rag_url)
# ======================================================
def start_cloudflare_tunnel(port, supabase_client):
    cmd = [r"D:/Fishy/server/cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]
    logger.info(f"[Cloudflare] Đang khởi động Tunnel cho Port {port}...")
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding="utf-8", errors="ignore",
        )
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        while True:
            line = process.stderr.readline()
            if not line: break
            match = url_pattern.search(line)
            if match:
                public_url = match.group(0)
                logger.info(f"[Cloudflare] TÌM THẤY LINK: {public_url}")
                try:
                    supabase_client.table("app_config").update(
                        {"value": public_url, "updated_at": datetime.now(timezone.utc).isoformat()}
                    ).eq("key", "rag_url").execute()
                    logger.info("[Cloudflare] Đã lưu link RAG lên Supabase thành công!")
                except Exception as e:
                    logger.error(f"[Cloudflare] Lỗi update Supabase: {e}")
                break
    except FileNotFoundError:
        logger.critical("LỖI: Không tìm thấy file 'cloudflared'.")
    except Exception as e:
        logger.error(f"[Cloudflare] Lỗi Cloudflare: {e}")

# ======================================================
# 3. LANGCHAIN CUSTOM RETRIEVER
# ======================================================
class LegalSupabaseRetriever(BaseRetriever):
    """
    Retriever tùy chỉnh của LangChain để gọi hàm RPC Supabase của bạn.
    """
    supabase_client: Any = Field(exclude=True)
    embedding_model: Any = Field(exclude=True)
    match_threshold: float = 0.45
    match_count: int = 10

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        # 1. Tạo Vector (Giữ nguyên tiền tố 'query: ')
        query_vector = self.embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        
        # 2. Gọi Supabase RPC v3
        rpc_res = self.supabase_client.rpc(
            "match_legal_docs_v3",
            {
                "query_embedding": query_vector,
                "query_text": query, # Yêu cầu cho tsvector lexical search
                "match_threshold": self.match_threshold,
                "match_count": self.match_count,
            },
        ).execute()

        hits = rpc_res.data or []
        
        # 3. Chuyển thành Document chuẩn LangChain
        docs = []
        for hit in hits:
            doc = Document(
                page_content=hit.get("noidung") or "",
                metadata={
                    "sothutund": hit.get("sothutund"),
                    "sohieu": hit.get("sohieu", "N/A"),
                    "hierarchy_path": hit.get("hierarchy_path", ""),
                    "similarity": hit.get("similarity", 0.0),
                }
            )
            docs.append(doc)
        
        return docs

# ======================================================
# 4. KHỞI TẠO APP & LANGCHAIN COMPONENTS
# ======================================================
app = FastAPI(title="LangChain Legal RAG API")

embedding_model = None
supabase = None
retriever = None
rag_chain = None

@app.on_event("startup")
def startup_event():
    global embedding_model, supabase, retriever, rag_chain
    logger.info("========== SERVER STARTUP ==========")

    logger.info(">> Loading embedding model (E5 Large)...")
    embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")

    logger.info(">> Connecting Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Khởi tạo Tunnel
    t = threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase))
    t.daemon = True
    t.start()

    # --- THIẾT LẬP LANGCHAIN PIPELINE ---
    logger.info(">> Configuring LangChain Pipeline...")
    
    # 1. Khởi tạo LLM Gemini qua LangChain
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
    
    # 2. Khởi tạo Custom Retriever
    retriever = LegalSupabaseRetriever(
        supabase_client=supabase, 
        embedding_model=embedding_model
    )

    # 3. Định nghĩa Prompt bằng ChatPromptTemplate (Có hỗ trợ Lịch sử)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Bạn là Trợ lý Luật Giao thông Việt Nam chuyên nghiệp.
NHIỆM VỤ: Trả lời câu hỏi dựa HOÀN TOÀN trên DỮ LIỆU PHÁP LUẬT bên dưới.
Nếu dữ liệu không có thông tin để trả lời, hãy lịch sự từ chối và xin lỗi vì chưa đủ dữ liệu.
Tuyệt đối không tự bịa ra mức phạt.

DỮ LIỆU PHÁP LUẬT:
{context}"""),
        MessagesPlaceholder(variable_name="history"), # Chỗ trống để chèn lịch sử chat
        ("human", "{question}")
    ])

    # 4. Hàm gom Context
    def format_docs(docs: List[Document]) -> str:
        if not docs: return ""
        formatted = []
        for d in docs:
            sohieu = d.metadata.get('sohieu', 'N/A')
            path = d.metadata.get('hierarchy_path', '')
            formatted.append(f"[Văn bản: {sohieu} | Cấu trúc: {path}]\n- {d.page_content}")
        return "\n\n".join(formatted)

    # 5. Ráp LCEL (LangChain Expression Language)
    rag_chain = (
        {
            "context": retriever | format_docs, 
            "question": RunnablePassthrough(),
            "history": RunnablePassthrough() # Lấy từ input dict
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    
    logger.info("========== SERVER READY ==========")

# ======================================================
# 5. ENDPOINTS
# ======================================================
class ChatRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = []

@app.get("/")
def health():
    return {"status": "Running", "framework": "LangChain + Supabase Custom Retriever"}

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    req_id = str(uuid.uuid4())[:8]
    logger.info(f"[{req_id}] Question: '{req.question}'")

    if rag_chain is None:
        return JSONResponse(status_code=503, content={"error": "LangChain chưa sẵn sàng..."})

    # Chuyển đổi lịch sử chat của Client thành chuẩn LangChain
    langchain_history = []
    for msg in req.history:
        if msg.get("role") == "user":
            langchain_history.append(HumanMessage(content=msg.get("content", "")))
        else:
            langchain_history.append(AIMessage(content=msg.get("content", "")))

    # Hàm Generator để Stream SSE
    async def generate():
        try:
            # Truyền dictionary vào chain
            input_dict = {
                "question": req.question,
                "history": langchain_history
            }
            
            # LangChain astream tự động xử lý toàn bộ luồng RAG
            async for chunk in rag_chain.astream(input_dict):
                safe_chunk = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {safe_chunk}\n\n"
            
            yield "data: [DONE]\n\n"
            logger.info(f"[{req_id}] Stream Finished.")
            
        except Exception as e:
            logger.exception(f"[{req_id}] LangChain Stream Error")
            yield f"data: [Lỗi hệ thống AI: {str(e)}]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)