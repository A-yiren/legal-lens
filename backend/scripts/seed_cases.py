"""类案入库脚本 - 把 seed_data_cases/*.jsonl 入库到 Qdrant + SQLite

用法：
  python3 scripts/seed_cases.py
"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any

# 让脚本能 import app
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.services.embedding import embedding_service
from app.storage.qdrant_client import vector_store
from app.storage.sqlite import db
from app.models import DocumentInfo, DocumentStatus, SourceType
from app.utils.logging import log


SEED_DIR = Path(__file__).parent.parent.parent / "seed_data_cases"
CASES_COLLECTION = "legal_cases"


def chunk_case(case: Dict) -> List[Dict[str, Any]]:
    """把一个案件切分成多个 chunk 用于向量化

    每个案件产生 3 个 chunk:
    - facts: 经审理查明
    - reasoning: 本院认为
    - judgment: 判决结果
    """
    chunks = []
    case_id = case["id"]
    sections = [
        ("facts", case.get("facts", "")),
        ("reasoning", case.get("reasoning", "")),
        ("judgment", case.get("judgment", "")),
    ]
    for idx, (chunk_type, text) in enumerate(sections):
        if not text or not text.strip():
            continue
        chunks.append({
            "chunk_id": f"{case_id}-c{idx:04d}",
            "case_id": case_id,
            "text": text,
            "chunk_type": chunk_type,
            "chunk_index": idx,
            "metadata": {
                "case_no": case.get("case_no", ""),
                "title": case.get("title", ""),
                "cause": case.get("cause", ""),
                "court": case.get("court", ""),
                "level": case.get("level", ""),
                "judgment_type": case.get("judgment_type", ""),
                "judgment_date": case.get("judgment_date", ""),
                "cited_articles": case.get("cited_articles", []),
                "amount": case.get("amount"),
                "win_probability_indicator": case.get("win_probability_indicator", ""),
                "tags": case.get("tags", []),
                "source": case.get("source", "seed"),
            }
        })
    return chunks


async def seed_cases():
    """入库所有 seed 案件"""
    if not SEED_DIR.exists():
        log.error(f"Seed 目录不存在: {SEED_DIR}")
        return

    # 1. 收集所有案件
    cases = []
    for fp in SEED_DIR.glob("*.jsonl"):
        with open(fp, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError as e:
                    log.warning(f"解析 {fp.name} 失败: {e}")

    log.info(f"共 {len(cases)} 个案件")

    # 2. 初始化 cases collection
    try:
        vector_store.init_collection(collection=CASES_COLLECTION)
    except Exception as e:
        log.warning(f"Collection 初始化失败: {e}")

    # 3. 切分 + Embedding + 入库
    total_chunks = 0
    for case in cases:
        case_id = case["id"]
        chunks = chunk_case(case)
        if not chunks:
            continue

        # 3.1 入库 SQLite (document 记录)
        try:
            doc_info = DocumentInfo(
                id=case_id,
                name=f"{case.get('title', 'unknown')}.case",
                source=SourceType.SEED,
                file_path=None,
                size=sum(len(c["text"]) for c in chunks),
                status=DocumentStatus.PROCESSING,
                chunks_count=len(chunks),
                metadata={
                    "file_type": "case",
                    "law_name": case.get("title", ""),
                    "case_no": case.get("case_no", ""),
                    "cause": case.get("cause", ""),
                    "court": case.get("court", ""),
                    "level": case.get("level", ""),
                    "judgment_type": case.get("judgment_type", ""),
                    "judgment_date": case.get("judgment_date", ""),
                    "cited_articles": case.get("cited_articles", []),
                    "amount": case.get("amount"),
                    "tags": case.get("tags", []),
                    "source": "seed_cases",
                }
            )
            doc_info.status = DocumentStatus.READY
            db.upsert_document(doc_info)
        except Exception as e:
            log.warning(f"SQLite 入库失败 {case_id}: {e}")
            continue

        # 3.2 Embedding + Qdrant
        try:
            texts = [c["text"] for c in chunks]
            t0 = time.time()
            embeddings = embedding_service.embed(texts)
            log.info(f"[Embedding] {case_id} {len(embeddings)} chunks, {time.time()-t0:.1f}s")

            # 3.3 构造 points
            points = []
            for c, emb in zip(chunks, embeddings):
                points.append({
                    "chunk_id": c["chunk_id"],
                    "text": c["text"],
                    "dense_vector": emb["dense"],
                    "sparse_vector": emb.get("sparse"),
                    "payload": {
                        "doc_id": case_id,
                        "case_id": case_id,
                        "case_no": c["metadata"]["case_no"],
                        "title": c["metadata"]["title"],
                        "cause": c["metadata"]["cause"],
                        "court": c["metadata"]["court"],
                        "level": c["metadata"]["level"],
                        "judgment_type": c["metadata"]["judgment_type"],
                        "judgment_date": c["metadata"]["judgment_date"],
                        "cited_articles": c["metadata"]["cited_articles"],
                        "amount": c["metadata"]["amount"],
                        "win_probability_indicator": c["metadata"]["win_probability_indicator"],
                        "tags": c["metadata"]["tags"],
                        "chunk_type": c["chunk_type"],
                        "chunk_index": c["chunk_index"],
                        "source_type": "case",  # 区分法律 vs 案件
                        "source": c["metadata"]["source"],
                        "text": c["text"],
                    }
                })

            # 3.4 批量入库
            vector_store.upsert_batch(points, collection=CASES_COLLECTION)
            total_chunks += len(chunks)
            log.info(f"[入库] {case.get('case_no', case_id)} {len(chunks)} chunks")

        except Exception as e:
            log.exception(f"案件入库失败 {case_id}: {e}")

    log.info(f"=== 完成: {len(cases)} 案件 / {total_chunks} chunks ===")


if __name__ == "__main__":
    asyncio.run(seed_cases())
