import os
import time
import asyncio
import logging
import uuid
import json
import httpx
import subprocess
import re
import threading
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from supabase import create_client
from sentence_transformers import SentenceTransformer

# ======================================================
# 1. CẤU HÌNH HỆ THỐNG
# ======================================================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

PORT_NUMBER = 8000 # Server RAG chạy port 8000

if not GEMINI_API_KEY:
    raise ValueError("LỖI: Chưa cấu hình GEMINI_API_KEY")

TOP_K_INITIAL = 10 
MATCH_THRESHOLD = 0.45

if not os.path.exists("logs"):
    os.makedirs("logs")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [%(levelname)s] | %(message)s",
    handlers=[
        logging.FileHandler(f"logs/server_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("RAG_SERVER")

# ======================================================
# 2. HÀM TỰ ĐỘNG CLOUDFLARE (Cập nhật rag_url)
# ======================================================
def start_cloudflare_tunnel(port, supabase_client):
    """
    Chạy cloudflared tunnel ngầm, bắt lấy link và up lên Supabase vào key 'rag_url'
    """
    # Lệnh chạy cloudflared.
    # Lưu ý: Đảm bảo file cloudflared.exe đã nằm trong thư mục code hoặc System32
    # Nếu file exe nằm cùng thư mục code thì dùng: cmd = [".\cloudflared.exe", "tunnel", "--url", f"http://localhost:{port}"]
    cmd = [r"D:/Fishy/server/cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]

    logger.info(f"[Cloudflare] Đang khởi động Tunnel cho Port {port}...")
    
    try:
        # Chạy tiến trình ngầm
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding='utf-8',
            errors='ignore' 
        )

        # Đọc log để tìm link
        public_url = None
        url_pattern = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')

        # Cloudflared in link ra stderr
        while True:
            line = process.stderr.readline()
            if not line:
                break
            
            match = url_pattern.search(line)
            if match:
                public_url = match.group(0)
                logger.info(f"[Cloudflare] TÌM THẤY LINK: {public_url}")
                
                # Update vào Supabase với key 'rag_url'
                try:
                    supabase_client.table("app_config").update({
                        "value": public_url,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("key", "rag_url").execute()
                    
                    logger.info("Đã lưu link RAG lên Supabase thành công!")
                except Exception as e:
                    logger.error(f"Lỗi update Supabase: {e}")
                break 
    except FileNotFoundError:
        logger.critical("LỖI: Không tìm thấy file 'cloudflared'. Hãy tải và cài đặt nó vào System32 hoặc thư mục dự án.")
    except Exception as e:
        logger.error(f"Lỗi Cloudflare Process: {e}")

# ======================================================
# 3. KHỞI TẠO APP
# ======================================================
app = FastAPI(title="Legal RAG API (Async HTTPX)")
embedding_model = None
supabase = None

@app.on_event("startup")
def startup_event():
    global embedding_model, supabase
    logger.info("========== SERVER STARTUP ==========")

    t0 = time.time()
    logger.info(">> Loading embedding model (E5 Large)...")
    embedding_model = SentenceTransformer("intfloat/multilingual-e5-large")
    logger.info(f">> Embedding loaded in {round(time.time()-t0, 2)}s")

    logger.info(">> Connecting Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Chạy Cloudflare Tunnel trong luồng riêng để không chặn server chính
    # Truyền biến supabase vào để tránh lỗi scope
    t = threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase))
    t.daemon = True # Thread sẽ tự tắt khi server tắt
    t.start()

    logger.info("========== SERVER READY ==========")

# ======================================================
# 4. MIDDLEWARE
# ======================================================
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"[{request_id}] {request.method} {request.url.path} | Done in {round(process_time, 3)}s")
    return response

# ======================================================
# 5. CORE LOGIC (RAG & GEMINI)
# ======================================================
class ChatRequest(BaseModel):
    question: str

def embed_query(text: str, req_id: str):
    t_start = time.time()
    vector = embedding_model.encode("query: " + text, normalize_embeddings=True).tolist()
    logger.info(f"[{req_id}] Embed created: {round(time.time()-t_start, 3)}s")
    return vector

def retrieve_docs_full_family(embedding, req_id: str):
    try:
        res = supabase.rpc(
            "match_legal_docs",
            {
                "query_embedding": embedding,
                "match_threshold": MATCH_THRESHOLD,
                "match_count": TOP_K_INITIAL
            }
        ).execute()
        
        initial_docs = res.data or []
        if not initial_docs:
            return []

        target_ids = set()
        for doc in initial_docs:
            target_ids.add(doc['sothutund'])
            parent_id = doc.get('sothutund_cha') or doc.get('r_parent')
            if parent_id:
                target_ids.add(parent_id)

        ids_to_fetch = list(target_ids)

        res_full = supabase.table("noidung") \
            .select("sothutund, noidung, sohieu, sothutund_cha") \
            .in_("sothutund", ids_to_fetch) \
            .execute()
        
        return res_full.data
    except Exception as e:
        logger.error(f"[{req_id}] Supabase Retrieval Error: {e}")
        return []

def pair_legal_docs(docs):
    doc_map = {d['sothutund']: d for d in docs}
    pairs = []
    consumed_ids = set()

    for doc in docs:
        p_id = doc.get('sothutund_cha')
        if p_id and p_id in doc_map:
            parent = doc_map[p_id]
            child = doc
            pairs.append({
                "type": "PAIR",
                "parent_id": parent['sothutund'],
                "parent_content": parent['noidung'].strip(),
                "child_id": child['sothutund'],
                "child_content": child['noidung'].strip(),
                "sohieu": child.get('sohieu', 'Quy định')
            })
            consumed_ids.add(child['sothutund'])
            consumed_ids.add(parent['sothutund'])

    for doc in docs:
        if doc['sothutund'] not in consumed_ids:
            pairs.append({
                "type": "SINGLE",
                "id": doc['sothutund'],
                "content": doc['noidung'].strip(),
                "sohieu": doc.get('sohieu', 'Quy định')
            })
    
    pairs.sort(key=lambda x: x.get('parent_id', x.get('id', 0)))
    return pairs

def build_prompt(question: str, context_str: str) -> str:
    if not context_str.strip():
        return f"""Bạn là Fishy - Trợ lý Luật Giao thông thông minh.
TÌNH HUỐNG: Không tìm thấy văn bản luật nào khớp trong database.
NHIỆM VỤ: Trả lời tự nhiên, thân thiện. Nếu hỏi luật, hãy xin lỗi.
CÂU HỎI: {question}"""

    return f"""Bạn là Trợ lý Luật Giao thông Việt Nam chuyên nghiệp.
NHIỆM VỤ: Trả lời câu hỏi dựa trên DỮ LIỆU CẶP (Hành vi + Mức phạt).
YÊU CẦU: Tổng hợp thành câu hoàn chỉnh, phân loại rõ ràng, trích dẫn nguồn.
DỮ LIỆU PHÁP LUẬT:
{context_str}
CÂU HỎI:
{question}
"""

async def stream_gemini_api(prompt: str, req_id: str):
    start_gen = time.time()
    logger.info(f"[{req_id}] Calling Gemini API (Async)...")

    MODEL_NAME = "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192 
        }
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=data) as response:
                
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"[{req_id}] Gemini Error: {error_body.decode()}")
                    yield f"data: [Lỗi API Google ({response.status_code})]\n\n"
                    return

                first_token = True
                logger.info(f"[{req_id}] --- GEMINI OUTPUT START ---")

                async for line in response.aiter_lines():
                    if line:
                        if line.startswith('data: '):
                            json_str = line[6:]
                            try:
                                chunk = json.loads(json_str)
                                if 'candidates' in chunk and len(chunk['candidates']) > 0:
                                    content = chunk['candidates'][0].get('content')
                                    if content and 'parts' in content:
                                        parts = content['parts']
                                        if parts:
                                            text_chunk = parts[0]['text']
                                            print(text_chunk, end="", flush=True)

                                            if first_token:
                                                logger.info(f"[{req_id}] TTFT: {round(time.time() - start_gen, 3)}s")
                                                first_token = False
                                            
                                            safe_chunk = json.dumps(text_chunk, ensure_ascii=False)
                                            yield f"data: {safe_chunk}\n\n"
                            except Exception:
                                continue
                
                print("\n")
                logger.info(f"[{req_id}] --- GEMINI OUTPUT END ---")
                yield "data: [DONE]\n\n"

    except Exception as e:
        logger.exception(f"[{req_id}] Connection Error")
        yield f"data: [Lỗi kết nối: {str(e)}]\n\n"

# ======================================================
# 6. ENDPOINTS
# ======================================================
@app.get("/")
def health():
    return {"status": "Running", "mode": "Async HTTPX (Cloudflare Tunnel)"}

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    req_id = getattr(request.state, "request_id", "UNKNOWN")
    logger.info(f"[{req_id}] Question: '{req.question}'")

    try:
        if embedding_model is None:
            return JSONResponse(status_code=503, content={"error": "Model đang tải..."})

        embedding = embed_query(req.question, req_id)
        raw_docs = retrieve_docs_full_family(embedding, req_id)
        context_str = ""
        
        if raw_docs:
            structured_pairs = pair_legal_docs(raw_docs)
            logger.info(f"[{req_id}] FOUND {len(structured_pairs)} RECORDS. RAG MODE ON.")
            for item in structured_pairs:
                sohieu_val = item.get('sohieu', 'Văn bản')
                if item['type'] == "PAIR":
                    context_str += f"\n--- CẶP DỮ LIỆU ---\n[Văn bản: {sohieu_val}]\n> HÀNH VI: {item['child_content']}\n> MỨC PHẠT: {item['parent_content']}\n-------------------\n"
                else:
                    context_str += f"\n--- DỮ LIỆU ĐƠN ---\n[Văn bản: {sohieu_val}]\n> Nội dung: {item['content']}\n-------------------\n"
        else:
            logger.info(f"[{req_id}] NO RECORDS FOUND. CHAT MODE ON.")

        prompt = build_prompt(req.question, context_str)
        return StreamingResponse(
            stream_gemini_api(prompt, req_id),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.exception(f"[{req_id}] Server Error")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    # Lưu ý: Khi chạy trực tiếp bằng python main.py thì nó sẽ dùng dòng này
    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)