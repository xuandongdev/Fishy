import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer
from supabase import create_client

from config.settings import RAGSettings
from router.chat_router import create_chat_router
from services.answer_service import AnswerService
from services.embedding_service import EmbeddingService
from services.firecrawl_service import FirecrawlService
from services.retrieval_service import RetrievalService
from services.trusted_web_cache_service import TrustedWebCacheService


logging.basicConfig(level=logging.INFO, format="%(asctime)s | [%(levelname)s] | %(message)s")

settings = RAGSettings.from_env()
supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
embedding_model = SentenceTransformer(settings.embedding_model_name)
trusted_cache_service = TrustedWebCacheService(supabase, settings)
embedding_service = EmbeddingService(settings)
answer_service = AnswerService(settings)
firecrawl_service = FirecrawlService(settings, trusted_cache_service, embedding_service)
retrieval_service = RetrievalService(
    supabase=supabase,
    embedding_model=embedding_model,
    settings=settings,
    trusted_cache_service=trusted_cache_service,
    firecrawl_service=firecrawl_service,
    answer_service=answer_service,
)

app = FastAPI(title="Fishy Trusted RAG API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(create_chat_router(retrieval_service))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("trusted_rag_app:app", host="0.0.0.0", port=settings.rag_port, reload=True)
