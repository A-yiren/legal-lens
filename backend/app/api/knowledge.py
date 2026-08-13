"""知识库 API"""
import shutil
import uuid
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query

from app.config import settings
from app.models import DocumentInfo, DocumentStatus, SourceType, SearchResult
from app.services.ingestion import ingestion_service
from app.services.retrieval import retrieval_service
from app.storage.sqlite import db
from app.utils.logging import log


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    source: str = Form(default="upload"),
    law_name: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
):
    """上传文档入库

    Args:
        file: 文件
        source: 来源（upload/seed/obsidian）
        law_name: 法律名称（可选，覆盖自动识别）
        tags: 标签，逗号分隔
    """
    # 校验
    if not file.filename:
        raise HTTPException(400, "文件名为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".pdf", ".docx", ".md", ".markdown", ".txt"):
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    # 保存到临时位置
    file_id = uuid.uuid4().hex[:12]
    save_name = f"{file_id}_{file.filename}"
    save_path = settings.upload_dir / save_name
    save_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with save_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        log.exception(f"保存文件失败: {e}")
        raise HTTPException(500, f"保存文件失败: {e}")

    # 入库
    extra = {}
    if law_name:
        extra["law_name"] = law_name
    if tags:
        extra["tags"] = [t.strip() for t in tags.split(",") if t.strip()]

    try:
        source_enum = SourceType(source)
    except ValueError:
        source_enum = SourceType.UPLOAD

    try:
        doc = await ingestion_service.ingest_file(
            save_path,
            source=source_enum,
            extra_metadata=extra,
        )
        return {
            "doc_id": doc.id,
            "name": doc.name,
            "chunks_count": doc.chunks_count,
            "status": doc.status.value,
            "law_name": doc.metadata.get("law_name"),
        }
    except Exception as e:
        log.exception(f"入库失败: {e}")
        raise HTTPException(500, f"入库失败: {e}")


@router.get("/documents")
async def list_documents(
    source: Optional[str] = None,
    limit: int = Query(100, le=500),
):
    """列出文档"""
    source_enum = None
    if source:
        try:
            source_enum = SourceType(source)
        except ValueError:
            pass
    docs = db.list_documents(source=source_enum, limit=limit)
    return [
        {
            "id": d.id,
            "name": d.name,
            "source": d.source.value,
            "size": d.size,
            "chunks_count": d.chunks_count,
            "status": d.status.value,
            "uploaded_at": d.uploaded_at.isoformat(),
            "metadata": d.metadata,
            # Phase 2: 顶层 source_url 方便 UI 直接显示
            "source_url": (d.metadata or {}).get("source_url"),
            "publisher": (d.metadata or {}).get("publisher"),
            "law_status": (d.metadata or {}).get("law_status"),
            "decree": (d.metadata or {}).get("decree"),
            "effective_date": (d.metadata or {}).get("effective_date"),
            "error": d.error,
        }
        for d in docs
    ]


@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: str,
    preview: bool = Query(False, description="是否返回文件前 500 字符预览"),
    preview_chars: int = Query(500, ge=50, le=5000, description="预览字符数"),
):
    """获取文档详情

    preview=true 时返回文件前 preview_chars 字符的纯文本预览，
    用于知识库页快速查看新增法律内容。
    """
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")

    result = {
        "id": doc.id,
        "name": doc.name,
        "source": doc.source.value,
        "file_path": doc.file_path,
        "size": doc.size,
        "chunks_count": doc.chunks_count,
        "status": doc.status.value,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "metadata": doc.metadata,
        # Phase 2: 顶层 source_url 方便 UI 直接显示
        "source_url": (doc.metadata or {}).get("source_url"),
        "publisher": (doc.metadata or {}).get("publisher"),
        "law_status": (doc.metadata or {}).get("law_status"),
        "decree": (doc.metadata or {}).get("decree"),
        "effective_date": (doc.metadata or {}).get("effective_date"),
        "error": doc.error,
    }

    if preview and doc.file_path:
        try:
            p = Path(doc.file_path)
            if p.exists() and p.is_file():
                # 文本类文件直接读前 N 字符
                if p.suffix.lower() in (".md", ".markdown", ".txt"):
                    text = p.read_text(encoding="utf-8", errors="ignore")
                elif p.suffix.lower() == ".docx":
                    # docx 简单提取前几段
                    try:
                        from docx import Document
                        d = Document(str(p))
                        text = "\n\n".join(par.text for par in d.paragraphs if par.text.strip())
                    except Exception:
                        text = ""
                elif p.suffix.lower() == ".pdf":
                    text = "(PDF 文件暂不支持在线预览，请下载查看)"
                else:
                    text = p.read_text(encoding="utf-8", errors="ignore")

                truncated = text[:preview_chars]
                result["preview"] = {
                    "text": truncated,
                    "total_chars": len(text),
                    "is_truncated": len(text) > preview_chars,
                    "truncated_at": min(preview_chars, len(text)),
                }
            else:
                result["preview"] = {"text": "(文件不存在或已被移动)", "total_chars": 0, "is_truncated": False, "truncated_at": 0}
        except Exception as e:
            log.exception(f"读取预览失败: {e}")
            result["preview"] = {"text": f"(读取失败: {e})", "total_chars": 0, "is_truncated": False, "truncated_at": 0}
    elif preview and doc_id.startswith("case-"):
        # 案件类（.case 文件）: 没有 file_path，从 Qdrant legal_cases 集合读 chunks
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            from app.storage.qdrant_client import vector_store
            points, _ = vector_store.client.scroll(
                collection_name="legal_cases",
                scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
                limit=20,
                with_payload=True,
                with_vectors=False,
            )
            # 按 chunk_index 排序
            points.sort(key=lambda p: p.payload.get("chunk_index", 0))
            # 拼接 facts / reasoning / judgment 三段
            parts = []
            for p in points:
                chunk_type = p.payload.get("chunk_type", "")
                text = p.payload.get("text", "").strip()
                if text:
                    label = {"facts": "【事实】", "reasoning": "【理由】", "judgment": "【判决】"}.get(chunk_type, f"【{chunk_type}】")
                    parts.append(f"{label}\n{text}")
            text = "\n\n".join(parts) if parts else "(案件暂无内容)"
            truncated = text[:preview_chars]
            result["preview"] = {
                "text": truncated,
                "total_chars": len(text),
                "is_truncated": len(text) > preview_chars,
                "truncated_at": min(preview_chars, len(text)),
            }
        except Exception as e:
            log.exception(f"读取案件预览失败: {e}")
            result["preview"] = {"text": f"(读取失败: {e})", "total_chars": 0, "is_truncated": False, "truncated_at": 0}

    return result


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档及其所有 chunks"""
    ok = ingestion_service.delete_document(doc_id)
    if not ok:
        raise HTTPException(404, "文档不存在或删除失败")
    return {"status": "deleted", "doc_id": doc_id}


@router.post("/search")
async def search_knowledge(
    query: str,
    top_k: int = Query(5, ge=1, le=50),
    law_name: Optional[str] = None,
    source: Optional[str] = None,
    use_rerank: bool = True,
):
    """知识库检索

    Args:
        query: 查询文本
        top_k: 返回数量
        law_name: 按法律名过滤
        source: 按来源过滤
        use_rerank: 是否使用重排序
    """
    filters = {}
    if law_name:
        filters["law_name"] = law_name
    if source:
        filters["source"] = source

    results = await retrieval_service.search(
        query=query,
        top_k=top_k,
        filters=filters if filters else None,
        use_rerank=use_rerank,
    )

    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "chunk_id": r.chunk_id,
                "text": r.text,
                "score": r.score,
                "law_name": r.law_name,
                "article_no": r.article_no,
                "citation": r.citation,
                "category": r.category,  # 知识库分类: law (法规) / case (案例)
                "metadata": r.metadata,
            }
            for r in results
        ]
    }


@router.post("/reindex")
async def reindex_all():
    """重建索引（重新生成所有向量）

    警告：会清空 Qdrant collection 并重建
    """
    from app.storage.qdrant_client import vector_store
    log.warning("[重建索引] 清空 collection 并重建")
    vector_store.init_collection(recreate=True)
    return {"status": "reindex_started", "message": "Collection 已重建，可重新上传文档"}
