"""文档解析器"""
from typing import List
from pathlib import Path
from app.models import Chunk
from app.parsers.base import BaseParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.docx_parser import DOCXParser
from app.parsers.md_parser import MDParser
from app.parsers.txt_parser import TXTParser


# 重导出方便外部
from app.parsers.legal_structure import LegalStructureParser


def get_parser(file_path: str | Path) -> BaseParser:
    """根据文件类型返回解析器"""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return PDFParser()
    elif ext == ".docx":
        return DOCXParser()
    elif ext in (".md", ".markdown"):
        return MDParser()
    elif ext == ".txt":
        return TXTParser()
    else:
        raise ValueError(f"不支持的文件类型: {ext}")


__all__ = ["get_parser", "BaseParser", "PDFParser", "DOCXParser", "MDParser", "TXTParser"]
