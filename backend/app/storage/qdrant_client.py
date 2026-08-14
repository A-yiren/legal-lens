"""Qdrant 向量库客户端 - 混合检索支持"""
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct, Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    Filter, FieldCondition, MatchValue, MatchAny, PayloadSchemaType,
)

from app.config import settings
from app.utils.logging import log


class QdrantVectorStore:
    """Qdrant 向量存储 - 支持本地持久化（无需外部 Docker）"""

    COLLECTION = settings.qdrant_collection
    DENSE_NAME = "dense"
    SPARSE_NAME = "sparse"

    def __init__(self):
        self._client: Optional[QdrantClient] = None
        self._initialized = False
        self._mode = "unknown"  # local/server/memory

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            # 优先尝试本地持久化模式（不需要 Docker）
            try:
                local_path = str(settings.qdrant_path)
                self._client = QdrantClient(path=local_path)
                self._mode = "local"
                log.info(f"Qdrant 本地模式: {local_path}")
            except Exception as e:
                log.warning(f"本地模式失败: {e}, 降级到内存模式")
                self._client = QdrantClient(location=":memory:")
                self._mode = "memory"
        return self._client

    def init_collection(self, recreate: bool = False, collection: Optional[str] = None):
        """初始化 collection - 默认 1024 维（BGE-M3 标准）"""
        target = collection or self.COLLECTION
        if self._initialized and not recreate and collection is None:
            return

        # 触发 client 初始化
        _ = self.client

        existing = [c.name for c in self.client.get_collections().collections]
        if target in existing:
            if recreate:
                self.client.delete_collection(target)
                log.info(f"删除已存在的 collection: {target}")
            else:
                self._initialized = True
                return

        # 使用配置中的默认维度（BGE-M3 = 1024）
        # 模型加载是懒加载，不阻塞启动
        dim = settings.embedding_dim
        log.info(f"使用维度: {dim}")

        self.client.create_collection(
            collection_name=target,
            vectors_config={
                self.DENSE_NAME: VectorParams(
                    size=dim,
                    distance=Distance.COSINE,
                ),
            },
        )
        # payload 索引（用于元数据过滤）
        for field in ("law_name", "status", "source", "doc_id", "case_id", "cause", "level", "source_type"):
            try:
                self.client.create_payload_index(
                    collection_name=target,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            except Exception as e:
                log.debug(f"创建 {field} 索引失败（可能已存在）: {e}")

        self._initialized = True
        log.info(f"Qdrant collection 已创建: {target} (dim={dim}, mode={self._mode})")

    def upsert(
        self,
        chunk_id: str,
        text: str,
        dense_vector: List[float],
        sparse_vector: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
    ):
        """插入或更新一个 chunk"""
        target = collection or self.COLLECTION
        point = PointStruct(
            id=self._qid(chunk_id),
            vector={
                self.DENSE_NAME: dense_vector,
            },
            payload={
                "chunk_id": chunk_id,
                "text": text,
                **(payload or {}),
            },
        )
        if sparse_vector and "indices" in sparse_vector:
            from qdrant_client.models import SparseVector
            point.vector[self.SPARSE_NAME] = SparseVector(
                indices=sparse_vector["indices"],
                values=sparse_vector["values"],
            )

        self.client.upsert(
            collection_name=target,
            points=[point],
        )

    def upsert_batch(self, points_data: List[Dict[str, Any]], collection: Optional[str] = None):
        """批量插入"""
        if not points_data:
            return
        target = collection or self.COLLECTION

        points = []
        for p in points_data:
            vector = {self.DENSE_NAME: p["dense_vector"]}
            if p.get("sparse_vector") and "indices" in p["sparse_vector"]:
                from qdrant_client.models import SparseVector
                vector[self.SPARSE_NAME] = SparseVector(
                    indices=p["sparse_vector"]["indices"],
                    values=p["sparse_vector"]["values"],
                )
            points.append(PointStruct(
                id=self._qid(p["chunk_id"]),
                vector=vector,
                payload={
                    "chunk_id": p["chunk_id"],
                    "text": p["text"],
                    **(p.get("payload") or {}),
                },
            ))

        self.client.upsert(
            collection_name=target,
            points=points,
        )
        log.info(f"批量入库: {len(points)} 个 chunks -> {target}")

    def search_dense(
        self,
        query_vector: List[float],
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """纯 dense 向量检索"""
        target = collection or self.COLLECTION
        qfilter = self._build_filter(filters)
        # 新版 Qdrant 客户端用 query_points + using 指定向量名
        if hasattr(self.client, 'query_points'):
            results = self.client.query_points(
                collection_name=target,
                query=query_vector,
                using=self.DENSE_NAME,
                query_filter=qfilter,
                limit=top_k,
                with_payload=True,
            )
            return [self._hit_to_dict(h) for h in results.points]
        # 旧版
        results = self.client.search(
            collection_name=target,
            query_vector=query_vector,
            query_filter=qfilter,
            limit=top_k,
            with_payload=True,
        )
        return [self._hit_to_dict(h) for h in results]

    def search_hybrid(
        self,
        dense_vector: List[float],
        sparse_vector: Optional[Dict[str, Any]] = None,
        top_k: int = 20,
        filters: Optional[Dict[str, Any]] = None,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """检索 - 当前为纯 dense 检索（sparse 模式暂未启用，rerank 阶段已经够好）"""
        return self.search_dense(dense_vector, top_k, filters, collection)

    def delete_by_doc(self, doc_id: str):
        """删除某个文档的所有 chunks"""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        self.client.delete(
            collection_name=self.COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        log.info(f"已删除 doc_id={doc_id} 的所有向量")

    def count(self, collection: Optional[str] = None) -> int:
        """总数"""
        target = collection or self.COLLECTION
        try:
            if hasattr(self.client, 'count'):
                result = self.client.count(collection_name=target)
                if hasattr(result, 'count'):
                    return result.count
                return result.get('count', 0) if isinstance(result, dict) else 0
            return 0
        except Exception as e:
            log.debug(f"count 失败: {e}")
            return 0

    def _qid(self, chunk_id: str) -> str:
        """Qdrant 需要 int 或 UUID 格式的 ID"""
        try:
            return str(uuid.UUID(chunk_id))
        except (ValueError, AttributeError):
            return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))

    def _hit_to_dict(self, hit) -> Dict[str, Any]:
        """将 Qdrant hit 转为 dict，保留所有 payload 字段"""
        payload = dict(hit.payload) if hit.payload else {}
        result = {
            "chunk_id": payload.get("chunk_id", ""),
            "text": payload.get("text", ""),
            "score": float(hit.score),
            # 保留完整 payload 作为溯源元数据，供 Citation 补全官方来源、
            # 发布机关、法律状态和生效日期。此前这些字段在此处被静默丢失。
            "metadata": {
                key: value for key, value in payload.items()
                if key not in {"chunk_id", "text"}
            },
            "law_name": payload.get("law_name"),
            "article_no": payload.get("article_no"),
            "article_title": payload.get("article_title"),
            "effective_date": payload.get("effective_date"),
            "status": payload.get("status"),
            "source": payload.get("source"),
            "doc_id": payload.get("doc_id"),
            "case_id": payload.get("case_id"),
            "case_no": payload.get("case_no"),
            "title": payload.get("title"),
            "cause": payload.get("cause"),
            "court": payload.get("court"),
            "level": payload.get("level"),
            "judgment_type": payload.get("judgment_type"),
            "judgment_date": payload.get("judgment_date"),
            "cited_articles": payload.get("cited_articles", []),
            "amount": payload.get("amount"),
            "win_probability_indicator": payload.get("win_probability_indicator"),
            "tags": payload.get("tags", []),
            "chunk_type": payload.get("chunk_type"),
            "source_type": payload.get("source_type"),
            "category": payload.get("category"),  # 知识库分类: law / case
        }
        return result

    def _rrf_fusion(self, dense_results, sparse_results, top_k: int, k: int = 60) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion"""
        scores: Dict[str, float] = {}
        hits_map: Dict[str, Any] = {}

        for rank, hit in enumerate(dense_results):
            chunk_id = hit.payload.get("chunk_id", str(hit.id))
            scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank + 1)
            hits_map[chunk_id] = hit

        for rank, hit in enumerate(sparse_results):
            chunk_id = hit.payload.get("chunk_id", str(hit.id))
            scores[chunk_id] = scores.get(chunk_id, 0) + 1.0 / (k + rank + 1)
            hits_map[chunk_id] = hit

        # 排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:top_k]
        results = []
        for chunk_id in sorted_ids:
            hit = hits_map[chunk_id]
            d = self._hit_to_dict(hit)
            d["score"] = scores[chunk_id]
            results.append(d)
        return results

    def _build_filter(self, filters: Optional[Dict[str, Any]]):
        if not filters:
            return None
        conditions = []
        for key, value in filters.items():
            if isinstance(value, list):
                conditions.append(FieldCondition(key=key, match=MatchAny(any=value)))
            else:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        if not conditions:
            return None
        return Filter(must=conditions)


# 全局实例
vector_store = QdrantVectorStore()
