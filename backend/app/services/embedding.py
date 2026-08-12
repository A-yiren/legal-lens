"""Embedding 服务 - BGE-M3 via sentence-transformers"""
import os
from typing import List, Dict, Any, Optional
from threading import Lock
from app.config import settings
from app.utils.logging import log


# 禁用 HuggingFace Hub 在线检查
os.environ.setdefault("HF_HUB_OFFLINE", "0")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")


class EmbeddingService:
    """BGE-M3 Embedding 服务 - 懒加载，支持 dense 模式"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.model = None
        self.use_sparse = False  # 标记是否支持 sparse
        self._initialized = True
        log.info("Embedding 服务初始化（懒加载）")

    def _load_model(self):
        if self.model is not None:
            return

        # 优先尝试 sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            log.info(f"加载 BGE-M3 (sentence-transformers): {settings.embedding_model}")
            self.model = SentenceTransformer(
                settings.embedding_model,
                device=settings.embedding_device,
                trust_remote_code=True,
            )
            self.use_sparse = False  # sentence-transformers 暂不支持 sparse 输出
            log.info("BGE-M3 加载完成 (dense only mode)")
        except ImportError:
            log.warning("sentence-transformers 未安装，将使用 mock embedding")
            self.model = "mock"
        except Exception as e:
            log.error(f"BGE-M3 加载失败: {e}, 降级到 mock")
            self.model = "mock"

    def embed(self, texts: List[str]) -> List[Dict[str, Any]]:
        """生成 embedding

        返回 [{"dense": List[float], "sparse": None}, ...]
        """
        if not texts:
            return []

        self._load_model()

        if self.model == "mock":
            return [self._mock_embed(t) for t in texts]

        try:
            # sentence-transformers 编码
            import numpy as np
            embeddings = self.model.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            results = []
            for i in range(len(texts)):
                dense = embeddings[i].tolist() if hasattr(embeddings[i], 'tolist') else list(embeddings[i])
                results.append({
                    "dense": dense,
                    "sparse": None,  # sentence-transformers 模式暂不支持 sparse
                })
            return results
        except Exception as e:
            log.exception(f"Embedding 生成失败: {e}")
            return [self._mock_embed(t) for t in texts]

    def _mock_embed(self, text: str) -> Dict[str, Any]:
        """Mock embedding - 简单的 hash 向量（仅供测试）"""
        import hashlib
        import numpy as np
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        np.random.seed(int(h[:8], 16) % (2**32))
        vec = np.random.randn(settings.embedding_dim).astype("float32").tolist()
        return {"dense": vec, "sparse": None}

    def get_dim(self) -> int:
        self._load_model()
        if self.model == "mock":
            return settings.embedding_dim
        try:
            return self.model.get_sentence_embedding_dimension()
        except Exception:
            return settings.embedding_dim


# 全局实例
embedding_service = EmbeddingService()
