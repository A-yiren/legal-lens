"""Reranker 服务 - 使用 sentence-transformers CrossEncoder"""
from typing import List, Tuple
from app.config import settings
from app.utils.logging import log


class RerankerService:
    """BGE-Reranker-v2-M3 重排序 - 用 sentence-transformers"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.model = None
        self._initialized = True

    def _load_model(self):
        if self.model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            log.info(f"加载 Reranker (CrossEncoder): {settings.rerank_model}")
            self.model = CrossEncoder(
                settings.rerank_model,
                device=settings.embedding_device,
                trust_remote_code=True,
            )
            log.info("Reranker 加载完成")
        except ImportError:
            log.warning("sentence-transformers 未安装，使用 mock reranker")
            self.model = "mock"
        except Exception as e:
            log.error(f"Reranker 加载失败: {e}, 使用 mock")
            self.model = "mock"

    def rerank(self, query: str, documents: List[str], top_k: int = None) -> List[Tuple[int, float]]:
        """重排序

        返回 [(doc_index, score), ...] 按 score 降序
        """
        if not documents:
            return []

        top_k = top_k or settings.rerank_final_k
        self._load_model()

        if self.model == "mock":
            results = []
            q_words = set(query)
            for i, doc in enumerate(documents):
                d_words = set(doc[:500])
                overlap = len(q_words & d_words)
                # mock 分数 = 0.5 + 词重合度归一化
                score = 0.5 + overlap / (len(q_words | d_words) + 1)
                results.append((i, score))
            results.sort(key=lambda x: -x[1])
            return results[:top_k]

        try:
            pairs = [[query, doc] for doc in documents]
            scores = self.model.predict(pairs, show_progress_bar=False)
            if hasattr(scores, 'tolist'):
                scores = scores.tolist()
            results = list(enumerate(scores))
            results.sort(key=lambda x: -x[1])
            return results[:top_k]
        except Exception as e:
            log.exception(f"Rerank 失败: {e}")
            return [(i, 1.0 - i * 0.01) for i in range(min(top_k, len(documents)))]


# 全局实例
reranker_service = RerankerService()
