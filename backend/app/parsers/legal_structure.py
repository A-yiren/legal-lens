"""法律领域结构化解析 - 识别条/款/项"""
import re
from typing import List, Dict, Any
from app.parsers.base import ParsedDocument, ParsedSection
from app.utils.logging import log


# 条文模式
ARTICLE_PATTERN = re.compile(r'第[零一二三四五六七八九十百千万亿〇\d]+条[之]?')
PARAGRAPH_PATTERN = re.compile(r'^[一二三四五六七八九十]+[、．]')
ITEM_PATTERN = re.compile(r'^[（(][一二三四五六七八九十\d]+[）)]')


class LegalStructureParser:
    """法律结构化解析器 - 识别条/款/项"""

    @staticmethod
    def extract_law_name(text: str, file_name: str = "") -> str:
        """从文本中提取法律名称"""
        # 优先从文件名
        if file_name:
            stem = file_name.rsplit(".", 1)[0]
            if any(kw in stem for kw in ["法", "条例", "规定", "办法", "解释", "意见"]):
                return stem

        # 从正文找
        patterns = [
            r'《([^》]+法)》',
            r'《([^》]+条例)》',
            r'《([^》]+规定)》',
            r'《([^》]+办法)》',
        ]
        for p in patterns:
            m = re.search(p, text[:2000])
            if m:
                return m.group(1)
        return file_name.rsplit(".", 1)[0] if file_name else "未知名法律"

    @staticmethod
    def parse_articles(text: str, law_name: str = "") -> List[Dict[str, Any]]:
        """解析条文结构

        返回：
        [{
            "article_no": "第五百七十七条",
            "article_text": "完整条文",
            "paragraphs": [{"text": "..."}],
            "items": [{"marker": "（一）", "text": "..."}],
            "position": (start_idx, end_idx)
        }, ...]
        """
        articles = []

        # 找所有条文位置
        matches = list(ARTICLE_PATTERN.finditer(text))
        if not matches:
            return []

        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            article_no = m.group()
            article_text = text[start:end].strip()

            # 移除条文编号本身
            content = re.sub(r'^第[零一二三四五六七八九十百千万亿〇\d]+条[之]?[\s\u3000]*', '', article_text)

            # 解析项
            items = []
            for im in ITEM_PATTERN.finditer(content):
                items.append({
                    "marker": im.group(),
                    "text": im.group(),  # 占位，实际值在下面补
                })

            articles.append({
                "article_no": article_no,
                "article_text": article_text,
                "content": content,
                "items": items,
                "position": (start, end),
            })

        return articles

    @classmethod
    def structure_chunks(cls, doc: ParsedDocument) -> List[Dict[str, Any]]:
        """将 ParsedDocument 转换为结构化的 chunk 列表

        每个 chunk 包含：
        - text: 内容
        - metadata: {law_name, article_no, article_title, ...}
        """
        law_name = cls.extract_law_name(doc.full_text, doc.metadata.get("file_name", ""))
        log.info(f"提取法律名称: {law_name}")

        chunks = []
        articles = cls.parse_articles(doc.full_text, law_name)

        if articles:
            # 法律文档：按条文切分
            log.info(f"识别为法律文档，共 {len(articles)} 条")
            for art in articles:
                chunks.append({
                    "text": art["article_text"],
                    "metadata": {
                        "law_name": law_name,
                        "article_no": art["article_no"],
                        "structure_type": "article",
                        "is_law": True,
                    }
                })
        else:
            # 非法律文档：按章节切分
            log.info("非结构化文档，按章节切分")
            for sec in doc.sections:
                if not sec.text.strip():
                    continue
                chunks.append({
                    "text": f"{sec.title}\n\n{sec.text}" if sec.title else sec.text,
                    "metadata": {
                        "title": sec.title,
                        "page": sec.page,
                        "is_law": False,
                        "law_name": law_name,
                    }
                })

        # 如果 chapters 为空（解析失败），整文做一个 chunk
        if not chunks and doc.full_text.strip():
            chunks.append({
                "text": doc.full_text,
                "metadata": {
                    "law_name": law_name,
                    "is_law": False,
                }
            })

        return chunks
