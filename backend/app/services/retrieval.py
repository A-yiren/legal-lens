"""检索服务 - 混合检索 + 重排序"""
import time
from typing import List, Dict, Any, Optional
from app.config import settings
from app.models import SearchResult
from app.services.embedding import embedding_service
from app.services.reranker import reranker_service
from app.storage.qdrant_client import vector_store
from app.utils.logging import log


class RetrievalService:
    """检索服务：Query → Embedding → 混合检索 → Rerank → Top-K"""

    def __init__(self):
        self.vector_store = vector_store
        self.embedding = embedding_service
        self.reranker = reranker_service

    async def search(
        self,
        query: str,
        top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        use_rerank: bool = True,
    ) -> List[SearchResult]:
        """检索

        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 元数据过滤 {law_name, status, source, ...}
            use_rerank: 是否使用重排序
        """
        top_k = top_k or settings.rerank_final_k
        log.info(f"[检索] query='{query[:50]}...' top_k={top_k} filters={filters}")

        # 1. Embedding
        t0 = time.time()
        embeddings = self.embedding.embed([query])
        if not embeddings:
            return []
        emb = embeddings[0]
        log.debug(f"Embedding 耗时: {time.time()-t0:.2f}s")

        # 2. 混合检索（召回 Top-20）
        retrieve_k = settings.rerank_top_k
        t0 = time.time()
        hits = self.vector_store.search_hybrid(
            dense_vector=emb["dense"],
            sparse_vector=emb.get("sparse"),
            top_k=retrieve_k,
            filters=filters,
        )
        log.debug(f"向量检索耗时: {time.time()-t0:.2f}s, 召回 {len(hits)}")

        if not hits:
            return []

        # 3. 重排序（默认关闭，避免大模型下载阻塞）
        if use_rerank and len(hits) > 1 and settings.use_rerank:
            t0 = time.time()
            docs = [h["text"] for h in hits]
            rerank_results = self.reranker.rerank(query, docs, top_k=top_k)
            log.debug(f"重排序耗时: {time.time()-t0:.2f}s")

            # 按 rerank 顺序返回
            results = []
            for idx, score in rerank_results:
                hit = hits[idx]
                hit["score"] = float(score)
                results.append(self._to_search_result(hit))
            return results
        else:
            return [self._to_search_result(h) for h in hits[:top_k]]

    def _to_search_result(self, hit: Dict[str, Any]) -> SearchResult:
        """统一格式"""
        law_name = hit.get("law_name", "")
        article_no = hit.get("article_no", "")
        citation = f"{law_name} {article_no}".strip()
        # 知识库分类: 默认 "law"，从 payload 中读 category 字段
        category = hit.get("category", "law")

        return SearchResult(
            chunk_id=hit["chunk_id"],
            text=hit["text"],
            score=hit.get("score", 0.0),
            metadata=hit.get("metadata", {}),
            law_name=law_name,
            article_no=article_no,
            citation=citation,
            category=category,
        )


# 全局实例
retrieval_service = RetrievalService()
