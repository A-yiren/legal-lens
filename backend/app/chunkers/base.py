"""切分器基类"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseChunker(ABC):
    """切分器基类"""

    @abstractmethod
    def chunk(self, parsed_doc, source_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """将 ParsedDocument 切分为 chunks

        返回：
        [{
            "text": str,
            "metadata": dict
        }, ...]
        """
        pass
