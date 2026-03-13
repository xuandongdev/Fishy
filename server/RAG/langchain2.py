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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from supabase import create_client
from sentence_transformers import SentenceTransformer

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("Chưa tìm thấy OPENAI_API_KEY trong .env")

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
                logger.info("SERVER ĐÃ HOẠT ĐỘNG! LINK ĐÃ ĐƯỢC CẬP NHẬT LÊN SUPABASE.\n\n")
                break
    except Exception as e: logger.error(f"Tunnel Error: {e}")

class LegalSupabaseRetriever(BaseRetriever):
    supabase_client: Any = Field(exclude=True)
    embedding_model: Any = Field(exclude=True)

    def extract_km(self, query: str) -> Optional[float]:
        pattern = r'(\d+(?:[\.,]\d+)?)\s*(?:km|km/h|cây số|cây|kỳ)|(?:quá|lố|chạy|mức|tốc độ)\s*(\d+(?:[\.,]\d+)?)'
        match = re.search(pattern, query, re.IGNORECASE)
        
        if match:
            val = match.group(1) if match.group(1) else match.group(2)
            try:
                num = float(val.replace(',', '.'))
                logger.info(f"ĐÃ TRÍCH XUẤT ĐƯỢC SỐ KM: {num}")
                return num
            except:
                return None
        return None

    def _get_relevant_documents(self, query: str) -> List[Document]:
        query_vector = self.embedding_model.encode("query: " + query, normalize_embeddings=True).tolist()
        
        # TRÍCH XUẤT SỐ KM
        query_km = self.extract_km(query)
        if query_km:
            logger.info(f"PHÁT HIỆN TRUY VẤN TỐC ĐỘ: {query_km} km/h")

        # Gọi RPC match_legal_docs_v2
        res = self.supabase_client.rpc("match_legal_docs_v2", {
            "vector_truy_van": query_vector,
            "van_ban_truy_van": query,
            "nguong_khop": 0.45,
            "so_luong_ket_qua": 10,
            "so_km_truy_van": query_km
        }).execute()
        
        data = res.data or []
        
        logger.info("\n" + "="*70)
        logger.info(f"USER: '{query}'")
        logger.info(f"TRUY XUẤT {len(data)} KẾT QUẢ:")
        
        for idx, item in enumerate(data):
            sohieu = item.get("sohieu", "N/A")
            noidung = item.get("noidung", "")
            terminal_line = noidung.split('\n')[-1]
            snippet = terminal_line[:100] + "..." if len(terminal_line) > 100 else terminal_line
            logger.info(f"   [{idx + 1}] {sohieu} | {snippet}")
        logger.info("="*70 + "\n")

        return [Document(
            page_content=h.get("noidung", ""), 
            metadata={
                "sohieu": h.get("sohieu"), 
                "path": h.get("duong_dan_phan_cap")
            }
        ) for h in data]

# Khởi tạo FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embedding_model = None
supabase = None
rag_chain = None

@app.on_event("startup")
def startup():
    global embedding_model, supabase, rag_chain
    embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase), daemon=True).start()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    
    retriever = LegalSupabaseRetriever(supabase_client=supabase, embedding_model=embedding_model)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Bạn là Trợ lý Luật Giao thông Fishy. Hãy trả lời dựa trên dữ liệu pháp luật được cung cấp.\n"
            "Khi có số liệu cụ thể (như tốc độ), hãy đối chiếu chính xác mức phạt.\n\n"
            "DỮ LIỆU LUẬT:\n{context}"
        )),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}")
    ])

    def format_docs(docs):
        return "\n\n".join([f"--- CĂN CỨ: {d.metadata.get('path', 'N/A')} ---\n{d.page_content}" for d in docs])

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
        logger.error(f"[LỖI LLM/SERVER] {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)