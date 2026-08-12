"""类案检索服务 - 复用现有 RAG 架构 + 案件专用过滤

数据源：
1. seed_data_cases/ 目录下的真实判例种子
2. 后续可接入 CAIL 2018 等公开数据集
3. 用户上传的判例
"""
import json
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.config import settings
from app.models.case import CaseInfo, CaseSearchResult, CaseCause
from app.services.embedding import embedding_service
from app.storage.qdrant_client import vector_store
from app.utils.logging import log


# Seed 数据目录
SEED_CASES_DIR = Path(__file__).parent.parent.parent / "seed_data_cases"


class CaseRetrievalService:
    """类案检索"""

    def __init__(self):
        self.vector_store = vector_store
        self.embedding = embedding_service
        self._collection_name = "legal_cases"

    async def search_similar_cases(
        self,
        query: str,
        top_k: int = 5,
        cause: Optional[str] = None,
        court_level: Optional[str] = None,
    ) -> List[CaseSearchResult]:
        """检索相似案件

        Args:
            query: 案情描述
            top_k: 返回数量
            cause: 按案由过滤（如 "合同纠纷"）
            court_level: 按法院级别过滤（如 "中级人民法院"）

        Returns:
            List[CaseSearchResult] 按相似度排序
        """
        # 1. Embedding
        embeddings = self.embedding.embed([query])
        if not embeddings:
            return []
        emb = embeddings[0]

        # 2. 构造 filter
        flt = {"source_type": "case"}
        if cause:
            flt["cause"] = cause
        if court_level:
            flt["level"] = court_level

        # 3. 向量检索
        try:
            hits = self.vector_store.search_hybrid(
                dense_vector=emb["dense"],
                sparse_vector=emb.get("sparse"),
                top_k=top_k * 2,  # 多召回一些，后面按案号去重
                filters=flt,
                collection=self._collection_name,
            )
        except Exception as e:
            log.warning(f"类案检索失败（可能 collection 还没建）: {e}")
            return []

        if not hits:
            return []

        # 4. 按 case_id 去重，保留最高相似度的 chunk
        best_per_case: Dict[str, Dict] = {}
        for h in hits:
            cid = h.get("case_id", h.get("chunk_id", ""))
            if not cid:
                continue
            if cid not in best_per_case or h.get("score", 0) > best_per_case[cid].get("score", 0):
                best_per_case[cid] = h

        # 5. 拼装结果
        results = []
        for case_id, hit in list(best_per_case.items())[:top_k]:
            results.append(CaseSearchResult(
                case_id=case_id,
                case_no=hit.get("case_no", ""),
                title=hit.get("title", ""),
                cause=hit.get("cause", ""),
                court=hit.get("court", ""),
                level=hit.get("level", ""),
                judgment_date=hit.get("judgment_date", ""),
                snippet=hit.get("text", "")[:300] + "..." if len(hit.get("text", "")) > 300 else hit.get("text", ""),
                score=hit.get("score", 0.0),
                cited_articles=hit.get("cited_articles", []),
                similarity_to_query=hit.get("score", 0.0),
            ))

        return results

    async def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """获取单条案件详情"""
        # TODO: 从 Qdrant 或 SQLite 取完整案件
        # 暂时从 seed jsonl 读
        cases = self._load_seed_cases()
        for c in cases:
            if c["id"] == case_id:
                return c
        return None

    def _load_seed_cases(self) -> List[Dict]:
        """从 seed jsonl 加载真实判例"""
        cases = []
        if not SEED_CASES_DIR.exists():
            return cases
        for fp in SEED_CASES_DIR.glob("*.jsonl"):
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        cases.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return cases


# 全局实例
case_retrieval = CaseRetrievalService()
