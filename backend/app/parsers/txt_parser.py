"""TXT 解析器"""
from pathlib import Path
from app.parsers.base import BaseParser, ParsedDocument, ParsedSection
from app.utils.logging import log


class TXTParser(BaseParser):
    """纯文本解析"""

    def parse(self, file_path: str | Path) -> ParsedDocument:
        path = Path(file_path)
        log.info(f"开始解析 TXT: {path.name}")

        # 尝试多种编码
        text = None
        for enc in ["utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"]:
            try:
                text = path.read_text(encoding=enc)
                log.debug(f"TXT 用 {enc} 解码成功: {path.name}")
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = path.read_bytes().decode("utf-8", errors="ignore")

        # 按空行分段
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        sections = [ParsedSection(title=path.stem, text=text, level=1)]

        metadata = {
            "file_name": path.name,
            "file_type": "txt",
            "paragraphs_count": len(paragraphs),
        }

        log.info(f"TXT 解析完成: {len(text)} 字符, {len(paragraphs)} 段落")
        return ParsedDocument(full_text=text, sections=sections, metadata=metadata)
