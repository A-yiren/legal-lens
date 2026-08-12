"""FastAPI 主入口"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from app.config import settings
from app.utils.logging import log
from app.storage.qdrant_client import vector_store
from app.api import health, knowledge, analyze, cases, obsidian


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动
    log.info(f"=== {settings.app_name} v{settings.app_version} 启动 ===")
    log.info(f"存储路径: {settings.storage_root}")
    log.info(f"Embedding 模型: {settings.embedding_model}")
    log.info(f"LLM: {settings.llm_provider}/{settings.llm_model}")

    # 初始化 Qdrant collection
    try:
        vector_store.init_collection()
        log.info(f"Qdrant collection 已就绪: {settings.qdrant_collection}")
    except Exception as e:
        log.warning(f"Qdrant 初始化失败（可能服务未启动）: {e}")

    yield

    # 关闭
    log.info("应用关闭")


# 创建 FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="律师专属 AI 案件分析平台 - 真实 RAG 引擎 + 引用溯源",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(health.router)
app.include_router(knowledge.router)
app.include_router(analyze.router)
app.include_router(cases.router)
app.include_router(obsidian.router)


# 静态前端（如果存在）
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    # 用 catch-all 路由接住 /pages/*.html 和 /*.html
    from fastapi import HTTPException

    @app.get("/")
    async def serve_index():
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "Frontend not built", "docs": "/docs"}

    @app.get("/index.html")
    async def serve_index_alias():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/pages/{page_name}")
    async def serve_page(page_name: str):
        """支持 /pages/case-analysis 和 /pages/case-analysis.html"""
        if not page_name.endswith(".html"):
            page_name = page_name + ".html"
        target = FRONTEND_DIR / "pages" / page_name
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        raise HTTPException(status_code=404, detail="Not Found")

    @app.get("/{name}.html")
    async def serve_html(name: str):
        target = FRONTEND_DIR / f"{name}.html"
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        raise HTTPException(status_code=404, detail="Not Found")

    # 静态资源（CSS/JS/图片等）
    @app.get("/static/{file_path:path}")
    async def serve_static(file_path: str):
        target = FRONTEND_DIR / file_path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        raise HTTPException(status_code=404, detail="Not Found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
