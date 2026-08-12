"""文档切分器"""
from app.chunkers.base import BaseChunker
from app.chunkers.legal_chunker import LegalChunker
from app.chunkers.semantic_chunker import SemanticChunker


def get_chunker(strategy: str = "legal") -> BaseChunker:
    """获取切分器"""
    if strategy == "legal":
        return LegalChunker()
    elif strategy == "semantic":
        return SemanticChunker()
    else:
        raise ValueError(f"未知切分策略: {strategy}")


__all__ = ["get_chunker", "BaseChunker", "LegalChunker", "SemanticChunker"]
