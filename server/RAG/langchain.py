import os
import logging
import uuid
import subprocess
import re
import threading
from typing import List, Any, Dict, Optional
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from supabase import create_client
from sentence_transformers import SentenceTransformer

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

# ======================================================
# CẤU HÌNH HỆ THỐNG
# ======================================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT_NUMBER = 8000 

logging.basicConfig(level=logging.INFO, format="%(asctime)s | [%(levelname)s] | %(message)s")
logger = logging.getLogger("LANGCHAIN_SERVER")

def start_cloudflare_tunnel(port, supabase_client):
    cmd = [r"D:/Fishy/server/cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        while True:
            line = process.stderr.readline()
            if not line: break
            match = url_pattern.search(line)
            if match:
                public_url = match.group(0)
                supabase_client.table("app_config").update(
                    {"value": public_url, "updated_at": datetime.now(timezone.utc).isoformat()}
                ).eq("key", "rag_url").execute()
                
                logger.info(f"[Cloudflare] RAG URL: {public_url}")
                # --- [YÊU CẦU 2]: IN LOG THÔNG BÁO SERVER ĐÃ SẴN SÀNG ---
                logger.info("SERVER ĐÃ HOẠT ĐỘNG.")
                break
    except Exception as e: logger.error(f"Tunnel Error: {e}")

class LegalSupabaseRetriever(BaseRetriever):
    supabase_client: Any = Field(exclude=True)
    embedding_model: Any = Field(exclude=True)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # Nhúng câu hỏi thành vector
        query_vector = self.embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        res = self.supabase_client.rpc("match_legal_docs_v3", {
            "query_embedding": query_vector,
            "query_text": query,
            "match_threshold": 0.45,
            "match_count": 10,
        }).execute()
        
        data = res.data or []
        
        # --- [YÊU CẦU 1]: IN KẾT QUẢ TỪ SUPABASE RA TERMINAL ---
        logger.info("\n\n" + "="*50)
        logger.info(f"🔍 CÂU HỎI TỪ APP: '{query}'")
        logger.info(f"📚 TÌM THẤY {len(data)} ĐIỀU LUẬT TỪ SUPABASE:")
        
        for idx, item in enumerate(data):
            sohieu = item.get("sohieu", "N/A")
            noidung = item.get("noidung", "")
            # Trích xuất 200 ký tự đầu tiên để Terminal không bị tràn chữ, dễ nhìn hơn
            snippet = noidung[:200] + "..." if len(noidung) > 200 else noidung
            logger.info(f"   [{idx + 1}] Số hiệu: {sohieu} | Nội dung: {snippet}")
        logger.info("="*50 + "\n")
        # ---------------------------------------------------------

        return [Document(page_content=h.get("noidung", ""), metadata={"sohieu": h.get("sohieu"), "path": h.get("hierarchy_path")}) for h in data]

app = FastAPI()
embedding_model = None
supabase = None
rag_chain = None

@app.on_event("startup")
def startup():
    global embedding_model, supabase, rag_chain
    embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase), daemon=True).start()

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
    retriever = LegalSupabaseRetriever(supabase_client=supabase, embedding_model=embedding_model)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "Bạn là Trợ lý Luật Giao thông Việt Nam chuyên nghiệp. Trả lời dựa trên dữ liệu pháp luật:\n\n{context}"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}")
    ])

    def format_docs(docs):
        return "\n\n".join([f"[Văn bản: {d.metadata.get('sohieu', 'N/A')}] {d.page_content}" for d in docs])

    rag_chain = (
        {
            "context": (lambda x: x["question"]) | retriever | format_docs, 
            "question": lambda x: x["question"], 
            "history": lambda x: x["history"]
        }
        | prompt | llm | StrOutputParser()
    )

class ChatRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = []

@app.post("/chat")
async def chat(req: ChatRequest):
    # Chuyển đổi lịch sử
    lang_hist = []
    for m in req.history:
        if m.get("role") == "user":
            lang_hist.append(HumanMessage(content=m.get("content", "")))
        else:
            lang_hist.append(AIMessage(content=m.get("content", "")))
            
    try:
        ans = await rag_chain.ainvoke({"question": req.question, "history": lang_hist})
        return {"answer": ans}
    except Exception as e:
        logger.error(f"[LỖI LLM/SERVER] {str(e)}") # Bổ sung log lỗi nếu LLM sập
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)