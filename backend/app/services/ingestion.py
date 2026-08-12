"""文档入库管道 - 解析→切分→Embedding→入库"""
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import settings
from app.models import DocumentInfo, DocumentStatus, SourceType
from app.parsers import get_parser
from app.parsers.legal_structure import LegalStructureParser
from app.chunkers import get_chunker
from app.services.embedding import embedding_service
from app.storage.sqlite import db
from app.storage.qdrant_client import vector_store
from app.utils.logging import log


class IngestionService:
    """文档入库管道"""

    def __init__(self):
        self.vector_store = vector_store
        # 确保 collection 存在（即使 lifespan 没跑也能工作）
        try:
            self.vector_store.init_collection()
        except Exception as e:
            log.warning(f"init_collection 在构造时失败: {e}")

    async def ingest_file(
        self,
        file_path: str | Path,
        source: SourceType = SourceType.UPLOAD,
        doc_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentInfo:
        """入库一个文件

        流程：
        1. 解析文件
        2. 切分
        3. Embedding
        4. 批量入库 Qdrant
        5. 写 SQLite 记录
        """
        path = Path(file_path)
        doc_id = doc_id or f"doc-{uuid.uuid4().hex[:12]}"
        extra_metadata = extra_metadata or {}

        log.info(f"[入库开始] {path.name} (doc_id={doc_id}, source={source.value})")

        # 1. 创建文档记录
        doc_info = DocumentInfo(
            id=doc_id,
            name=path.name,
            source=source,
            file_path=str(path.absolute()) if path.exists() else None,
            size=path.stat().st_size if path.exists() else 0,
            status=DocumentStatus.PROCESSING,
        )
        db.upsert_document(doc_info)

        try:
            # 2. 解析
            parser = get_parser(path)
            parsed = parser.parse(path)
            log.info(f"[解析完成] {path.name}: {len(parsed.full_text)} 字符, {len(parsed.sections)} 章节")

            # 提取法律名称（如果适用）
            if "is_law" not in extra_metadata:
                law_name = LegalStructureParser.extract_law_name(parsed.full_text, path.name)
                extra_metadata["law_name"] = law_name

            # 提取 frontmatter 字段（source_url / source_domain / publisher / law_status / decree / enact_date / effective_date）
            # Phase 2: 让每个 chunk 都能追溯到官方源
            frontmatter = parsed.metadata.get("frontmatter") or {}
            if isinstance(frontmatter, dict):
                for fm_key in ("source_url", "source_domain", "publisher", "law_status", "original_law_name",
                                "decree", "enact_date", "effective_date", "scraped_at"):
                    fm_val = frontmatter.get(fm_key)
                    if fm_val and fm_key not in extra_metadata:
                        # date / datetime 转 ISO 字符串，避免 json.dumps 序列化失败
                        if hasattr(fm_val, "isoformat"):
                            fm_val = fm_val.isoformat()
                        extra_metadata[fm_key] = fm_val

            # 3. 切分
            chunker = get_chunker("legal")
            chunks_data = chunker.chunk(parsed, source_metadata={
                "doc_id": doc_id,
                "source": source.value,
                "file_name": path.name,
                **extra_metadata,
            })

            if not chunks_data:
                raise ValueError("文档切分结果为空")

            log.info(f"[切分完成] {len(chunks_data)} chunks")

            # 4. Embedding
            texts = [c["text"] for c in chunks_data]
            t0 = time.time()
            embeddings = embedding_service.embed(texts)
            log.info(f"[Embedding 完成] {len(embeddings)} 个, 耗时 {time.time()-t0:.1f}s")

            # 5. 构造入库数据
            points_data = []
            for i, (chunk_data, emb) in enumerate(zip(chunks_data, embeddings)):
                chunk_id = f"{doc_id}-c{i:04d}"
                meta = chunk_data.get("metadata", {})
                points_data.append({
                    "chunk_id": chunk_id,
                    "text": chunk_data["text"],
                    "dense_vector": emb["dense"],
                    "sparse_vector": emb.get("sparse"),
                    "payload": {
                        "doc_id": doc_id,
                        "source": source.value,
                        "chunk_index": i,
                        "text": chunk_data["text"],
                        **meta,
                    }
                })

            # 6. 批量入库 Qdrant
            self.vector_store.upsert_batch(points_data)

            # 7. 更新文档状态
            doc_info.status = DocumentStatus.READY
            doc_info.chunks_count = len(points_data)
            # Phase 2: 持久化 frontmatter 字段（包括 source_url）到 doc_info.metadata
            doc_meta = {"file_type": parsed.metadata.get("file_type"), "law_name": extra_metadata.get("law_name")}
            for fm_key in ("source_url", "source_domain", "publisher", "law_status", "original_law_name",
                            "decree", "enact_date", "effective_date", "scraped_at"):
                if fm_key in extra_metadata:
                    doc_meta[fm_key] = extra_metadata[fm_key]
            doc_info.metadata = doc_meta
            db.upsert_document(doc_info)

            log.info(f"[入库完成] {path.name} → {len(points_data)} chunks")
            return doc_info

        except Exception as e:
            log.exception(f"[入库失败] {path.name}: {e}")
            doc_info.status = DocumentStatus.FAILED
            doc_info.error = str(e)[:500]
            db.upsert_document(doc_info)
            raise

    async def ingest_text(
        self,
        text: str,
        name: str = "inline_text",
        source: SourceType = SourceType.UPLOAD,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentInfo:
        """入库纯文本（用于 Obsidian / API 输入）"""
        from app.parsers.base import ParsedDocument
        from app.chunkers import get_chunker

        doc_id = f"doc-{uuid.uuid4().hex[:12]}"
        metadata = metadata or {}

        doc_info = DocumentInfo(
            id=doc_id,
            name=name,
            source=source,
            status=DocumentStatus.PROCESSING,
        )
        db.upsert_document(doc_info)

        try:
            parsed = ParsedDocument(
                full_text=text,
                sections=[],
                metadata={"file_name": name, "file_type": "text"},
            )

            chunker = get_chunker("legal")
            chunks_data = chunker.chunk(parsed, source_metadata={
                "doc_id": doc_id,
                "source": source.value,
                **metadata,
            })

            if not chunks_data:
                raise ValueError("切分结果为空")

            texts = [c["text"] for c in chunks_data]
            embeddings = embedding_service.embed(texts)

            points_data = []
            for i, (chunk_data, emb) in enumerate(zip(chunks_data, embeddings)):
                chunk_id = f"{doc_id}-c{i:04d}"
                meta = chunk_data.get("metadata", {})
                points_data.append({
                    "chunk_id": chunk_id,
                    "text": chunk_data["text"],
                    "dense_vector": emb["dense"],
                    "sparse_vector": emb.get("sparse"),
                    "payload": {
                        "doc_id": doc_id,
                        "source": source.value,
                        "chunk_index": i,
                        "text": chunk_data["text"],
                        **meta,
                    }
                })

            self.vector_store.upsert_batch(points_data)

            doc_info.status = DocumentStatus.READY
            doc_info.chunks_count = len(points_data)
            doc_info.metadata = metadata
            db.upsert_document(doc_info)

            log.info(f"[文本入库完成] {name} → {len(points_data)} chunks")
            return doc_info

        except Exception as e:
            log.exception(f"[文本入库失败] {name}: {e}")
            doc_info.status = DocumentStatus.FAILED
            doc_info.error = str(e)[:500]
            db.upsert_document(doc_info)
            raise

    def delete_document(self, doc_id: str) -> bool:
        """删除文档及其所有 chunks"""
        try:
            self.vector_store.delete_by_doc(doc_id)
            return db.delete_document(doc_id)
        except Exception as e:
            log.exception(f"删除文档失败: {e}")
            return False


# 全局实例
ingestion_service = IngestionService()
