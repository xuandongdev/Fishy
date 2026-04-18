import logging
import os
import re
import subprocess
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer
from supabase import Client, create_client

from config.settings import RAGSettings
from langchain_adapter import LangChainAdapter
from router.chat_router import create_chat_router
from services.answer_service import AnswerService
from services.conversation_manager import ConversationManager
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.firecrawl_service import FirecrawlService
from services.global_doc_service import GlobalDocService
from services.qdrant_service import QdrantService
from services.retrieval_service import RetrievalService
from services.session_doc_service import SessionDocService
from services.trusted_web_cache_service import TrustedWebCacheService


logging.basicConfig(level=logging.INFO, format="%(asctime)s | [%(levelname)s] | %(message)s")
logger = logging.getLogger("TRUSTED_RAG_APP")

settings = RAGSettings.from_env()
supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
embedding_model = SentenceTransformer(settings.embedding_model_name)
answer_service = AnswerService(settings)
embedding_service = EmbeddingService(settings, embedding_model=embedding_model)
trusted_cache_service = TrustedWebCacheService(supabase, settings)
firecrawl_service = FirecrawlService(settings, trusted_cache_service, embedding_service)
document_parser_service = DocumentParserService()
qdrant_service = QdrantService(settings, vector_size=embedding_service.vector_size)
session_doc_service = SessionDocService(
    settings=settings,
    parser_service=document_parser_service,
    embedding_service=embedding_service,
    qdrant_service=qdrant_service,
)
global_doc_service = GlobalDocService(
    settings=settings,
    parser_service=document_parser_service,
    embedding_service=embedding_service,
    qdrant_service=qdrant_service,
)
retrieval_service = RetrievalService(
    supabase=supabase,
    embedding_model=embedding_model,
    settings=settings,
    trusted_cache_service=trusted_cache_service,
    firecrawl_service=firecrawl_service,
    session_doc_service=session_doc_service,
    global_doc_service=global_doc_service,
    answer_service=answer_service,
)
conversation_manager = ConversationManager()
langchain_adapter = LangChainAdapter(
    retrieval_service=retrieval_service,
    answer_service=answer_service,
    conversation_manager=conversation_manager,
    settings=settings,
)

CLOUDFLARED_PATH = os.getenv("CLOUDFLARED_PATH", r"D:/Fishy/server/cloudflared.exe")


def start_cloudflare_tunnel(port: int, supabase_client: Client) -> None:
    cmd = [CLOUDFLARED_PATH, "tunnel", "--url", f"http://127.0.0.1:{port}"]
    logger.info("[Cloudflare] Dang khoi dong tunnel cho trusted_rag (port %s)...", port)

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
            if not match:
                continue

            public_url = match.group(0)
            logger.info("[Cloudflare] RAG URL: %s", public_url)
            try:
                supabase_client.table("app_config").upsert(
                    {
                        "key": "rag_url",
                        "value": public_url,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="key",
                ).execute()
                logger.info("[Cloudflare] Da luu rag_url len Supabase.")
            except Exception as exc:
                logger.warning("[Cloudflare] Khong the cap nhat rag_url: %s", exc)
            break
    except FileNotFoundError:
        logger.warning(
            "[Cloudflare] Khong tim thay cloudflared tai %s. trusted_rag van chay local tren port %s.",
            CLOUDFLARED_PATH,
            port,
        )
    except Exception as exc:
        logger.warning("[Cloudflare] Tunnel trusted_rag loi: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    qdrant_service.ensure_collections()
    if settings.supabase_url and settings.supabase_service_role_key:
        threading.Thread(
            target=start_cloudflare_tunnel,
            args=(settings.rag_port, supabase),
            daemon=True,
        ).start()
    else:
        logger.info("Bo qua trusted_rag Cloudflare vi thieu thong tin Supabase.")

    yield


app = FastAPI(title="Fishy Trusted RAG API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(
    create_chat_router(
        retrieval_service,
        langchain_adapter=langchain_adapter,
        session_doc_service=session_doc_service,
        global_doc_service=global_doc_service,
    )
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("trusted_rag_app:app", host="0.0.0.0", port=settings.rag_port, reload=True)
