"""解析器基类"""
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ParsedSection:
    """解析后的章节"""
    title: str = ""
    text: str = ""
    level: int = 0  # 标题层级
    page: int = 0  # PDF 页码
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析后的文档"""
    full_text: str  # 完整文本
    sections: List[ParsedSection]  # 章节
    metadata: Dict[str, Any]  # 文档元数据
    total_pages: int = 0  # 页数（PDF）


class BaseParser(ABC):
    """解析器基类"""

    @abstractmethod
    def parse(self, file_path: str | Path) -> ParsedDocument:
        """解析文件"""
        pass

    def _make_doc_id(self, file_path: str | Path) -> str:
        """从文件路径生成 doc_id"""
        from app.utils.text import content_hash
        import time
        return f"doc-{content_hash(str(file_path))}-{int(time.time() * 1000) % 100000}"
