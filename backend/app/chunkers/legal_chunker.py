"""法律文档切分器 - 按条文章节切分"""
import uuid
from typing import List, Dict, Any
from app.chunkers.base import BaseChunker
from app.parsers.base import ParsedDocument
from app.parsers.legal_structure import LegalStructureParser
from app.utils.text import chunk_text
from app.utils.logging import log


class LegalChunker(BaseChunker):
    """法律文档切分 - 优先按条文，太长再按字符切分"""

    def __init__(self, max_chars: int = 1024, overlap: int = 64):
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, parsed_doc: ParsedDocument, source_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        source_metadata = source_metadata or {}

        # 1. 尝试结构化切分
        chunks = LegalStructureParser.structure_chunks(parsed_doc)

        # 2. 对每个 chunk，如果太长再切
        final_chunks = []
        for c in chunks:
            text = c["text"]
            meta = {**c.get("metadata", {}), **source_metadata}

            if len(text) <= self.max_chars:
                final_chunks.append({"text": text, "metadata": meta})
            else:
                # 切分
                sub_texts = chunk_text(text, self.max_chars, self.overlap)
                for i, sub in enumerate(sub_texts):
                    sub_meta = {**meta, "part": i + 1, "total_parts": len(sub_texts)}
                    final_chunks.append({"text": sub, "metadata": sub_meta})

        log.info(f"切分完成: {len(chunks)} → {len(final_chunks)} chunks")
        return final_chunks
