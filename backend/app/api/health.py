"""健康检查"""
from fastapi import APIRouter
from app.config import settings
from app.storage.sqlite import db
from app.storage.qdrant_client import vector_store


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    """健康检查"""
    qdrant_status = "unknown"
    vector_count = 0
    try:
        vector_count = vector_store.count()
        qdrant_status = "ok"
    except Exception as e:
        qdrant_status = f"error: {e}"

    doc_count = len(db.list_documents(limit=10000))
    case_count = len(db.list_cases(limit=10000))

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "qdrant": qdrant_status,
        "vector_count": vector_count,
        "doc_count": doc_count,
        "case_count": case_count,
        "embedding_model": settings.embedding_model,
        "llm_model": settings.llm_model,
        "llm_provider": settings.llm_provider,
    }


@router.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
