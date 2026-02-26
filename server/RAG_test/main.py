import os
import time
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

PORT_NUMBER = 8000  # Server RAG chạy port 8000

TOP_K_INITIAL = 10
MATCH_THRESHOLD = 0.45

# LOG control (đỡ spam nếu cần)
LOG_HIT_PREVIEW_CHARS = 220
LOG_CONTEXT_PREVIEW_CHARS = 1800
LOG_TOP_HITS_DETAIL = 5  # log chi tiết top N hits
LOG_PAIR_PREVIEW = 5     # log preview top N pairs

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
        logging.FileHandler(
            f"logs/server_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("RAG_SERVER")

# ======================================================
# 2. HÀM TỰ ĐỘNG CLOUDFLARE (Cập nhật rag_url)
# ======================================================
def start_cloudflare_tunnel(port, supabase_client):
    """
    Chạy cloudflared tunnel ngầm, bắt lấy link và up lên Supabase vào key 'rag_url'
    """
    cmd = [r"D:/Fishy/server/cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]

    logger.info(f"[Cloudflare] Đang khởi động Tunnel cho Port {port}...")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="ignore",
        )

        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

        while True:
            line = process.stderr.readline()
            if not line:
                break

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
        logger.critical(
            "LỖI: Không tìm thấy file 'cloudflared'. Hãy cài đặt hoặc sửa đường dẫn cmd."
        )
    except Exception as e:
        logger.error(f"[Cloudflare] Lỗi Cloudflare Process: {e}")

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
    logger.info(f">> Embedding loaded in {round(time.time() - t0, 2)}s")

    logger.info(">> Connecting Supabase...")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Cloudflare tunnel
    t = threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase))
    t.daemon = True
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
    logger.info(f"[{req_id}] Embed created: {round(time.time() - t_start, 3)}s")
    return vector

def _clean_preview(s: str, limit: int) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        return s[:limit] + "..."
    return s

def retrieve_docs_full_family(embedding, req_id: str):
    """
    Trả về:
      - hits: danh sách kết quả từ RPC match_legal_docs (GIỮ THỨ TỰ + similarity)
      - family_docs: danh sách record từ bảng noidung cho (hit + parent) để build context
    """
    try:
        rpc_res = supabase.rpc(
            "match_legal_docs_v3",
            {
                "query_embedding": embedding,
                "query_text": req.question,
                "match_threshold": MATCH_THRESHOLD,
                "match_count": TOP_K_INITIAL,
            },
        ).execute()

        hits = rpc_res.data or []
        if not hits:
            logger.info(f"[{req_id}] RETRIEVE: hits=0")
            return [], []

        # Giữ nguyên thứ tự hits để eval
        ranked_hits = []
        for h in hits:
            ranked_hits.append(
                {
                    "sothutund": h.get("sothutund"),
                    "similarity": float(h.get("similarity", 0.0)),
                    "sohieu": h.get("sohieu"),
                    "hierarchy_path": h.get("hierarchy_path"),
                    "sothutund_cha": h.get("sothutund_cha"),
                    # RPC có trả noidung -> log preview để debug retrieval
                    "noidung_preview": _clean_preview(h.get("noidung") or "", LOG_HIT_PREVIEW_CHARS),
                }
            )

        top_ids = [x["sothutund"] for x in ranked_hits[:5]]
        top_sims = [round(x["similarity"], 4) for x in ranked_hits[:5]]
        logger.info(f"[{req_id}] RETRIEVE: hits={len(ranked_hits)} top_ids={top_ids} top_sims={top_sims}")

        # Log chi tiết top N hit
        for i, x in enumerate(ranked_hits[:LOG_TOP_HITS_DETAIL], start=1):
            logger.info(
                f"[{req_id}] HIT#{i} id={x['sothutund']} sim={x['similarity']:.4f} "
                f"sohieu={x.get('sohieu')} path={x.get('hierarchy_path')} "
                f"parent={x.get('sothutund_cha')} preview='{x.get('noidung_preview')}'"
            )

        # Family expansion: fetch hit + parent từ bảng noidung để ghép cặp
        target_ids = set()
        for h in hits:
            doc_id = h.get("sothutund")
            if doc_id is not None:
                target_ids.add(doc_id)

            parent_id = h.get("sothutund_cha")
            if parent_id:
                target_ids.add(parent_id)

        ids_to_fetch = list(target_ids)
        table_res = (
            supabase.table("noidung")
            .select("sothutund, noidung, sohieu, sothutund_cha")
            .in_("sothutund", ids_to_fetch)
            .execute()
        )
        family_docs = table_res.data or []

        logger.info(f"[{req_id}] FAMILY_FETCH: ids={len(ids_to_fetch)} rows={len(family_docs)}")

        return ranked_hits, family_docs

    except Exception as e:
        logger.error(f"[{req_id}] Supabase Retrieval Error: {e}")
        return [], []

def pair_legal_docs(docs):
    doc_map = {d["sothutund"]: d for d in docs if d.get("sothutund") is not None}
    pairs = []
    consumed_ids = set()

    for doc in docs:
        p_id = doc.get("sothutund_cha")
        if p_id and p_id in doc_map:
            parent = doc_map[p_id]
            child = doc
            pairs.append(
                {
                    "type": "PAIR",
                    "parent_id": parent["sothutund"],
                    "parent_content": (parent.get("noidung") or "").strip(),
                    "child_id": child["sothutund"],
                    "child_content": (child.get("noidung") or "").strip(),
                    "sohieu": child.get("sohieu", "Quy định"),
                }
            )
            consumed_ids.add(child["sothutund"])
            consumed_ids.add(parent["sothutund"])

    for doc in docs:
        if doc.get("sothutund") not in consumed_ids:
            pairs.append(
                {
                    "type": "SINGLE",
                    "id": doc.get("sothutund"),
                    "content": (doc.get("noidung") or "").strip(),
                    "sohieu": doc.get("sohieu", "Quy định"),
                }
            )

    pairs.sort(key=lambda x: x.get("parent_id", x.get("id", 0)) or 0)
    return pairs

def build_prompt(question: str, context_str: str) -> str:
    if not context_str.strip():
        return f"""Bạn là Fishy - Trợ lý Luật Giao thông thông minh.
TÌNH HUỐNG: Không tìm thấy văn bản luật nào khớp trong database nội bộ.
NHIỆM VỤ: Trả lời tự nhiên, thân thiện. Nếu câu hỏi yêu cầu trích dẫn điều luật/mức phạt cụ thể thì hãy xin lỗi vì chưa có đủ dữ liệu.
CÂU HỎI: {question}"""

    return f"""Bạn là Trợ lý Luật Giao thông Việt Nam chuyên nghiệp.
NHIỆM VỤ: Trả lời câu hỏi dựa trên DỮ LIỆU PHÁP LUẬT bên dưới.
YÊU CẦU:
- Chỉ sử dụng thông tin có trong dữ liệu.
- Nếu có thể, nêu rõ hành vi và mức phạt/tác động tương ứng.
- Viết rõ ràng, có gạch đầu dòng nếu cần.

DỮ LIỆU PHÁP LUẬT:
{context_str}

CÂU HỎI:
{question}
"""

async def stream_gemini_api(prompt: str, req_id: str):
    start_gen = time.time()
    logger.info(f"[{req_id}] Calling Gemini API (Async)...")

    MODEL_NAME = "gemini-2.5-flash"
    # NOTE: Không log URL đầy đủ để tránh lộ API key
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=data) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"[{req_id}] Gemini Error status={response.status_code} body={error_body.decode(errors='ignore')}")
                    yield f"data: [Lỗi API Google ({response.status_code})]\n\n"
                    return

                first_token = True
                logger.info(f"[{req_id}] --- GEMINI OUTPUT START ---")

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    if line.startswith("data: "):
                        json_str = line[6:]
                        try:
                            chunk = json.loads(json_str)
                            if "candidates" in chunk and chunk["candidates"]:
                                content = chunk["candidates"][0].get("content")
                                if content and "parts" in content and content["parts"]:
                                    text_chunk = content["parts"][0].get("text", "")
                                    if not text_chunk:
                                        continue

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

        # STEP 1 - PHASE 1
        hits, family_docs = retrieve_docs_full_family(embedding, req_id)

        context_str = ""
        if family_docs:
            structured_pairs = pair_legal_docs(family_docs)
            logger.info(f"[{req_id}] FOUND {len(structured_pairs)} RECORDS. RAG MODE ON.")

            # Log preview pair để thấy server đang ghép gì
            for i, item in enumerate(structured_pairs[:LOG_PAIR_PREVIEW], start=1):
                if item["type"] == "PAIR":
                    logger.info(
                        f"[{req_id}] PAIR#{i} child_id={item['child_id']} parent_id={item['parent_id']} "
                        f"child='{_clean_preview(item['child_content'], 160)}' "
                        f"parent='{_clean_preview(item['parent_content'], 160)}'"
                    )
                else:
                    logger.info(
                        f"[{req_id}] SINGLE#{i} id={item['id']} content='{_clean_preview(item['content'], 220)}'"
                    )

            for item in structured_pairs:
                sohieu_val = item.get("sohieu", "Văn bản")
                if item["type"] == "PAIR":
                    context_str += (
                        f"\n--- CẶP DỮ LIỆU ---\n"
                        f"[Văn bản: {sohieu_val}]\n"
                        f"> HÀNH VI: {item['child_content']}\n"
                        f"> MỨC PHẠT: {item['parent_content']}\n"
                        f"-------------------\n"
                    )
                else:
                    context_str += (
                        f"\n--- DỮ LIỆU ĐƠN ---\n"
                        f"[Văn bản: {sohieu_val}]\n"
                        f"> Nội dung: {item['content']}\n"
                        f"-------------------\n"
                    )

            # Log preview context_str để chắc chắn prompt có dữ liệu
            logger.info(f"[{req_id}] CONTEXT_PREVIEW:\n{context_str[:LOG_CONTEXT_PREVIEW_CHARS]}")
        else:
            logger.info(f"[{req_id}] NO RECORDS FOUND. CHAT MODE ON.")
            logger.info(f"[{req_id}] CONTEXT_PREVIEW: <EMPTY>")

        # Log top1 sim để phục vụ Phase 2 (abstain)
        if hits:
            logger.info(f"[{req_id}] TOP1_SIM={hits[0]['similarity']:.4f} TOP1_ID={hits[0]['sothutund']}")
        else:
            logger.info(f"[{req_id}] TOP1_SIM=<NONE>")

        prompt = build_prompt(req.question, context_str)
        return StreamingResponse(stream_gemini_api(prompt, req_id), media_type="text/event-stream")

    except Exception as e:
        logger.exception(f"[{req_id}] Server Error")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)
