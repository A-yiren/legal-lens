"""文本处理工具"""
import re
import hashlib
from typing import List


def normalize_text(text: str) -> str:
    """归一化文本"""
    # 合并多余空白
    text = re.sub(r'\s+', ' ', text)
    # 去除控制字符
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """通用文本切分（按字符）"""
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # 尝试在句末切分
        if end < text_len:
            for sep in ['。', '！', '？', '\n', ';', '；']:
                last_sep = text.rfind(sep, start, end)
                if last_sep > start + chunk_size // 2:
                    end = last_sep + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break
        start = max(end - overlap, start + 1)

    return chunks


def content_hash(content: str) -> str:
    """内容哈希（用于去重）"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]


def extract_citation_marker(text: str) -> List[str]:
    """从文本中提取引用标记 [1][2][3]"""
    return re.findall(r'\[(\d+)\]', text)


def truncate(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix
