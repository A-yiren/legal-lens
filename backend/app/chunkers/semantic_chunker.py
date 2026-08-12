"""通用语义切分器 - 按段落+字符"""
import uuid
from typing import List, Dict, Any
from app.chunkers.base import BaseChunker
from app.parsers.base import ParsedDocument
from app.utils.text import chunk_text, normalize_text
from app.utils.logging import log


class SemanticChunker(BaseChunker):
    """按段落 + 字符滑动窗口"""

    def __init__(self, max_chars: int = 512, overlap: int = 64):
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, parsed_doc: ParsedDocument, source_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        source_metadata = source_metadata or {}
        text = normalize_text(parsed_doc.full_text)

        # 优先按段落切分
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

        chunks = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) + 2 <= self.max_chars:
                current = (current + "\n\n" + p) if current else p
            else:
                if current:
                    chunks.append(current)
                if len(p) > self.max_chars:
                    # 太长，再切
                    sub = chunk_text(p, self.max_chars, self.overlap)
                    chunks.extend(sub[:-1])
                    current = sub[-1] if sub else ""
                else:
                    current = p
        if current:
            chunks.append(current)

        log.info(f"Semantic 切分完成: {len(chunks)} chunks")
        return [{"text": c, "metadata": {"is_law": False, **source_metadata}} for c in chunks]
