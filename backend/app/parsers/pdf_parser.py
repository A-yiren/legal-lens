"""PDF 解析器"""
from pathlib import Path
from app.parsers.base import BaseParser, ParsedDocument, ParsedSection
from app.utils.logging import log


class PDFParser(BaseParser):
    """PDF 解析 - 使用 PyMuPDF"""

    def parse(self, file_path: str | Path) -> ParsedDocument:
        import fitz  # PyMuPDF

        path = Path(file_path)
        log.info(f"开始解析 PDF: {path.name}")

        doc = fitz.open(str(path))
        sections = []
        full_text_parts = []

        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            if not text.strip():
                continue
            full_text_parts.append(text)
            sections.append(ParsedSection(
                title=f"第{page_num}页",
                text=text,
                level=2,
                page=page_num,
            ))

        full_text = "\n\n".join(full_text_parts)
        metadata = {
            "file_name": path.name,
            "file_type": "pdf",
            "total_pages": len(doc),
        }

        # PDF metadata
        try:
            pdf_meta = doc.metadata
            if pdf_meta:
                for key in ["title", "author", "subject", "keywords", "creator"]:
                    if pdf_meta.get(key):
                        metadata[key] = pdf_meta[key]
        except Exception:
            pass

        doc.close()
        log.info(f"PDF 解析完成: {len(sections)} 页, {len(full_text)} 字符")
        return ParsedDocument(
            full_text=full_text,
            sections=sections,
            metadata=metadata,
            total_pages=len(sections),
        )
