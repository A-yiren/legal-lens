"""Markdown 解析器 - 支持 Obsidian 语法"""
import re
from pathlib import Path
from app.parsers.base import BaseParser, ParsedDocument, ParsedSection
from app.utils.logging import log


class MDParser(BaseParser):
    """Markdown 解析 - 支持 frontmatter、双向链接、标签"""

    def parse(self, file_path: str | Path) -> ParsedDocument:
        path = Path(file_path)
        log.info(f"开始解析 MD: {path.name}")

        content = path.read_text(encoding="utf-8")

        # 解析 frontmatter
        frontmatter, body = self._parse_frontmatter(content)

        # 提取双向链接
        wiki_links = self._extract_wiki_links(body)

        # 提取标签
        tags = self._extract_tags(body)

        # 解析章节（按 # ## ### 标题）
        sections = self._parse_sections(body, path.stem)

        metadata = {
            "file_name": path.name,
            "file_type": "md",
            "frontmatter": frontmatter,
            "wiki_links": wiki_links,
            "tags": tags,
        }

        log.info(f"MD 解析完成: {len(sections)} 章节, {len(wiki_links)} 链接, {len(tags)} 标签")
        return ParsedDocument(
            full_text=body,
            sections=sections,
            metadata=metadata,
        )

    def _parse_frontmatter(self, content: str) -> tuple[dict, str]:
        """解析 YAML frontmatter"""
        if not content.startswith("---"):
            return {}, content
        try:
            end = content.index("---", 3)
            yaml_text = content[3:end].strip()
            body = content[end+3:].lstrip("\n")
            import yaml
            return yaml.safe_load(yaml_text) or {}, body
        except (ValueError, ImportError, Exception):
            return {}, content

    def _extract_wiki_links(self, text: str) -> list[tuple[str, str]]:
        """提取 [[双向链接]]，返回 [(target, alias)]"""
        pattern = r'\[\[([^\]]+)\]\]'
        links = []
        for match in re.finditer(pattern, text):
            inner = match.group(1)
            if "|" in inner:
                target, alias = inner.split("|", 1)
            else:
                target, alias = inner, inner
            links.append((target.strip(), alias.strip()))
        return links

    def _extract_tags(self, text: str) -> list[str]:
        """提取 #标签（排除代码块内）"""
        # 简单实现：找 #xxx
        pattern = r'(?<![\w/])#([\w\u4e00-\u9fa5/-]+)'
        tags = []
        for match in re.finditer(pattern, text):
            tag = match.group(1)
            if "/" in tag or "-" in tag or tag.isalnum() or any('\u4e00' <= c <= '\u9fff' for c in tag):
                tags.append(tag)
        return list(set(tags))

    def _parse_sections(self, body: str, default_title: str) -> list[ParsedSection]:
        """按标题切分章节"""
        lines = body.split("\n")
        sections = []
        current_title = default_title
        current_text = []
        current_level = 1

        for line in lines:
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                # 切换章节
                if current_text or current_title != default_title:
                    sections.append(ParsedSection(
                        title=current_title,
                        text="\n".join(current_text).strip(),
                        level=current_level,
                    ))
                current_level = len(m.group(1))
                current_title = m.group(2).strip()
                current_text = []
            else:
                current_text.append(line)

        # 最后一个章节
        if current_text or current_title != default_title:
            sections.append(ParsedSection(
                title=current_title,
                text="\n".join(current_text).strip(),
                level=current_level,
            ))

        # 过滤空章节
        return [s for s in sections if s.text or s.title != default_title]
