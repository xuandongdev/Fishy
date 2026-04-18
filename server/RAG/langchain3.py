import logging
import os
import re
import subprocess
import threading
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.retrievers import BaseRetriever
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

PORT_NUMBER = int(os.getenv("RAG_PORT", "8000"))
EMBEDDING_MODEL_NAME = os.getenv("HF_EMBED_MODEL", "intfloat/multilingual-e5-large")
CROSS_ENCODER_MODEL_NAME = os.getenv("CROSS_ENCODER_MODEL", "BAAI/bge-reranker-v2-m3")
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.45"))
CANDIDATE_K = int(os.getenv("RERANK_CANDIDATE_K", "20"))
FINAL_K = int(os.getenv("RERANK_FINAL_K", "5"))
RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "16"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | [%(levelname)s] | %(message)s")
logger = logging.getLogger("LANGCHAIN3_SERVER")

TRAFFIC_KEYWORDS = (
    "giao thong",
    "duong bo",
    "xe may",
    "xe mo to",
    "oto",
    "o to",
    "xe hoi",
    "xe tai",
    "xe con",
    "lai xe",
    "bang lai",
    "giay phep lai xe",
    "dang ki xe",
    "giay dang ky xe",
    "bien so",
    "csgt",
    "canh sat giao thong",
    "vuot den do",
    "den do",
    "toc do",
    "vuot toc do",
    "nong do con",
    "lan duong",
    "nguoc chieu",
    "diem bang lai",
    "mu bao hiem",
    "tai nan giao thong",
    "phuong tien",
    "dung xe",
    "do xe",
    "phat nguoi",
)


def start_cloudflare_tunnel(port: int, supabase_client: Any) -> None:
    cmd = [r"D:/Fishy/server/cloudflared.exe", "tunnel", "--url", f"http://127.0.0.1:{port}"]
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        while True:
            line = process.stderr.readline()
            if not line:
                break
            match = url_pattern.search(line)
            if match:
                public_url = match.group(0)
                supabase_client.table("app_config").update(
                    {"value": public_url, "updated_at": datetime.now(timezone.utc).isoformat()}
                ).eq("key", "rag_url").execute()
                logger.info("[Cloudflare] RAG URL: %s", public_url)
                logger.info("Server da san sang va da cap nhat link len Supabase.")
                break
    except Exception as exc:
        logger.error("Tunnel error: %s", exc)


def load_embedding_model(model_name: str) -> SentenceTransformer:
    try:
        return SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        return SentenceTransformer(model_name)


def load_reranker_model(model_name: str) -> CrossEncoder:
    try:
        return CrossEncoder(model_name, local_files_only=True, max_length=512)
    except Exception:
        return CrossEncoder(model_name, max_length=512)


def normalize_query_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def is_traffic_related_query(text: str) -> bool:
    normalized = normalize_query_text(text)
    if not normalized.strip():
        return False

    if re.search(r"\b\d+(?:[\.,]\d+)?\s*(?:km/h|kmh|km)\b", normalized):
        return True

    return any(keyword in normalized for keyword in TRAFFIC_KEYWORDS)


def should_use_traffic_rag(question: str, history: Optional[List[Dict[str, str]]] = None) -> bool:
    recent_user_messages: List[str] = []
    for item in reversed(history or []):
        if item.get("role") == "user" and item.get("content"):
            recent_user_messages.append(item["content"])
            if len(recent_user_messages) >= 2:
                break

    combined_text = " ".join(list(reversed(recent_user_messages)) + [question])
    return is_traffic_related_query(combined_text)


class LegalSupabaseRetriever(BaseRetriever):
    supabase_client: Any = Field(exclude=True)
    embedding_model: Any = Field(exclude=True)
    reranker_model: Any = Field(exclude=True)
    match_threshold: float = MATCH_THRESHOLD
    candidate_k: int = CANDIDATE_K
    final_k: int = FINAL_K
    rerank_batch_size: int = RERANK_BATCH_SIZE

    def extract_km(self, query: str) -> Optional[float]:
        normalized_query = normalize_query_text(query)
        pattern = (
            r"(\d+(?:[\.,]\d+)?)\s*(?:km/h|kmh|km|cay so|cay)"
            r"|(?:qua|lo|chay|muc|toc do|vuot)\s*(\d+(?:[\.,]\d+)?)"
        )
        match = re.search(pattern, normalized_query, re.IGNORECASE)
        if not match:
            return None

        raw_value = match.group(1) or match.group(2)
        if not raw_value:
            return None

        try:
            value = float(raw_value.replace(",", "."))
            logger.info("Trich xuat so km tu truy van: %s", value)
            return value
        except ValueError:
            return None

    def rerank_hits(self, query: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not hits:
            return []

        pairs = [(query, item.get("noidung", "")) for item in hits]
        scores = self.reranker_model.predict(
            pairs,
            batch_size=self.rerank_batch_size,
            show_progress_bar=False,
        )

        reranked_hits: List[Dict[str, Any]] = []
        for index, (item, score) in enumerate(zip(hits, scores), start=1):
            enriched = dict(item)
            enriched["cross_score"] = float(score)
            enriched["candidate_rank"] = index
            reranked_hits.append(enriched)

        reranked_hits.sort(key=lambda item: item["cross_score"], reverse=True)
        return reranked_hits[: self.final_k]

    def log_hits(self, title: str, hits: List[Dict[str, Any]], score_key: str) -> None:
        logger.info("%s (%s ket qua)", title, len(hits))
        for idx, item in enumerate(hits, start=1):
            snippet = (item.get("noidung") or "").split("\n")[-1][:100]
            logger.info(
                "   [%s] id=%s | score=%s | sohieu=%s | %s",
                idx,
                item.get("sothutund", "N/A"),
                round(float(item.get(score_key, 0.0)), 4),
                item.get("sohieu", "N/A"),
                snippet,
            )

    def _get_relevant_documents(self, query: str) -> List[Document]:
        query_vector = self.embedding_model.encode(
            "query: " + query,
            normalize_embeddings=True,
        ).tolist()

        query_km = self.extract_km(query)
        res = self.supabase_client.rpc(
            "match_legal_docs_v4",
            {
                "vector_truy_van": query_vector,
                "van_ban_truy_van": query,
                "nguong_khop": self.match_threshold,
                "so_luong_ket_qua": self.candidate_k,
                "so_km_truy_van": query_km,
            },
        ).execute()

        candidate_hits = res.data or []
        logger.info("=" * 72)
        logger.info("USER: %s", query)
        logger.info(
            "Hybrid retrieval tra ve %s candidate, threshold=%s, candidate_k=%s, final_k=%s",
            len(candidate_hits),
            self.match_threshold,
            self.candidate_k,
            self.final_k,
        )
        self.log_hits("Top candidate truoc rerank", candidate_hits[: min(5, len(candidate_hits))], "do_tuong_dong")

        final_hits = candidate_hits
        if self.reranker_model and candidate_hits:
            try:
                final_hits = self.rerank_hits(query, candidate_hits)
                self.log_hits("Top ket qua sau cross-encoder rerank", final_hits, "cross_score")
            except Exception as exc:
                logger.exception("Rerank that bai, fallback ve thu tu retrieval goc: %s", exc)
                final_hits = candidate_hits[: self.final_k]
        else:
            final_hits = candidate_hits[: self.final_k]

        logger.info("=" * 72)
        return [
            Document(
                page_content=item.get("noidung", ""),
                metadata={
                    "sothutund": item.get("sothutund"),
                    "sohieu": item.get("sohieu"),
                    "path": item.get("duong_dan_phan_cap"),
                    "do_tuong_dong": item.get("do_tuong_dong"),
                    "cross_score": item.get("cross_score"),
                    "sothutund_cha": item.get("sothutund_cha"),
                },
            )
            for item in final_hits
        ]


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

embedding_model = None
reranker_model = None
supabase = None
rag_chain = None
general_chain = None


@app.on_event("startup")
def startup() -> None:
    global embedding_model, reranker_model, supabase, rag_chain, general_chain

    if not OPENAI_API_KEY:
        logger.warning("Chua tim thay OPENAI_API_KEY trong .env")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Thieu SUPABASE_URL hoac SUPABASE_SERVICE_ROLE_KEY trong .env")

    logger.info("Dang load embedding model: %s", EMBEDDING_MODEL_NAME)
    embedding_model = load_embedding_model(EMBEDDING_MODEL_NAME)

    logger.info("Dang load reranker model: %s", CROSS_ENCODER_MODEL_NAME)
    reranker_model = load_reranker_model(CROSS_ENCODER_MODEL_NAME)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    threading.Thread(target=start_cloudflare_tunnel, args=(PORT_NUMBER, supabase), daemon=True).start()

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    retriever = LegalSupabaseRetriever(
        supabase_client=supabase,
        embedding_model=embedding_model,
        reranker_model=reranker_model,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "Ban la Tro ly Luat Giao thong Fishy. Hay tra loi dua tren du lieu phap luat duoc cung cap.\n"
                    "Khi co so lieu cu the nhu toc do, hay doi chieu chinh xac muc phat.\n\n"
                    "DU LIEU LUAT:\n{context}"
                ),
            ),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ]
    )

    def format_docs(docs: List[Document]) -> str:
        return "\n\n".join(
            [
                f"--- CAN CU: {doc.metadata.get('path', 'N/A')} ---\n{doc.page_content}"
                for doc in docs
            ]
        )

    rag_chain = (
        {
            "context": (lambda x: x["question"]) | retriever | format_docs,
            "question": lambda x: x["question"],
            "history": lambda x: x["history"],
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    general_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "Ban la tro ly AI huu ich. Neu cau hoi khong lien quan den luat giao thong duong bo, "
                    "hay tra loi binh thuong dua tren kien thuc chung va lap luan ro rang. "
                    "Neu khong chac chan, hay noi ro gioi han cua cau tra loi."
                ),
            ),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ]
    )

    general_chain = (
        {
            "question": lambda x: x["question"],
            "history": lambda x: x["history"],
        }
        | general_prompt
        | llm
        | StrOutputParser()
    )


class ChatRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = []


@app.post("/chat")
async def chat(req: ChatRequest) -> Dict[str, str]:
    lang_hist: List[Any] = []
    for item in req.history:
        if item.get("role") == "user":
            lang_hist.append(HumanMessage(content=item.get("content", "")))
        else:
            lang_hist.append(AIMessage(content=item.get("content", "")))

    try:
        use_traffic_rag = should_use_traffic_rag(req.question, req.history)
        selected_chain = rag_chain if use_traffic_rag else general_chain
        logger.info(
            "Router chon che do: %s",
            "traffic_rag" if use_traffic_rag else "general_api",
        )
        answer = await selected_chain.ainvoke({"question": req.question, "history": lang_hist})
        return {"answer": answer}
    except Exception as exc:
        logger.error("Loi LLM/server: %s", exc)
        return JSONResponse(status_code=500, content={"error": str(exc)})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT_NUMBER)
