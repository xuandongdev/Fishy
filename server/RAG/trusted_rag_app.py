import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer
from supabase import create_client

from config.settings import RAGSettings
from langchain_adapter import LangChainAdapter
from router.chat_router import create_chat_router
from services.answer_service import AnswerService
from services.conversation_manager import ConversationManager
from services.document_parser_service import DocumentParserService
from services.embedding_service import EmbeddingService
from services.global_doc_service import GlobalDocService
from services.retrieval_service import RetrievalService


logging.basicConfig(level=logging.INFO, format="%(asctime)s | [%(levelname)s] | %(message)s")
logger = logging.getLogger("TRUSTED_RAG_APP")

settings = RAGSettings.from_env()
supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
embedding_model = SentenceTransformer(settings.embedding_model_name)
answer_service = AnswerService(settings)
embedding_service = EmbeddingService(settings, embedding_model=embedding_model)
document_parser_service = DocumentParserService()

global_doc_service = GlobalDocService(
    supabase=supabase,
    settings=settings,
    parser_service=document_parser_service,
    embedding_service=embedding_service,
)

retrieval_service = RetrievalService(
    supabase=supabase,
    embedding_model=embedding_model,
    settings=settings,
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


app = FastAPI(title="Fishy Trusted RAG API", version="1.0.0")
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
        global_doc_service=global_doc_service,
    )
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("trusted_rag_app:app", host="0.0.0.0", port=settings.rag_port, reload=True)
