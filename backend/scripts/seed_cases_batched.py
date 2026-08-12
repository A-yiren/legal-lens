"""分批入库案件 - 防止 OOM（每批 5 个案件 + 30 秒让系统 GC）"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.services.embedding import embedding_service
from app.storage.qdrant_client import vector_store
from app.storage.sqlite import db
from app.models import DocumentInfo, DocumentStatus, SourceType
from app.utils.logging import log


SEED_DIR = Path(__file__).parent.parent.parent / "seed_data_cases"
CASES_COLLECTION = "legal_cases"
BATCH_SIZE = 5  # 2G 内存：每批 5 个


def chunk_case(case):
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


async def seed_batched():
    if not SEED_DIR.exists():
        log.error(f"Seed 目录不存在: {SEED_DIR}")
        return

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

    log.info(f"共 {len(cases)} 个案件，分 {len(cases)//BATCH_SIZE + 1} 批入库（每批 {BATCH_SIZE}）")

    # Init collection 一次
    try:
        vector_store.init_collection(collection=CASES_COLLECTION)
    except Exception as e:
        log.warning(f"Collection 初始化: {e}")

    total_chunks = 0
    for batch_start in range(0, len(cases), BATCH_SIZE):
        batch = cases[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(cases) + BATCH_SIZE - 1) // BATCH_SIZE
        log.info(f"\n=== 批次 {batch_num}/{total_batches}（{len(batch)} 个案件）===")

        for case in batch:
            case_id = case["id"]
            chunks = chunk_case(case)
            if not chunks:
                continue

            # SQLite
            try:
                doc_info = DocumentInfo(
                    id=case_id,
                    name=f"{case.get('title', 'unknown')}.case",
                    source=SourceType.SEED,
                    file_path=None,
                    size=sum(len(c["text"]) for c in chunks),
                    status=DocumentStatus.READY,
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
                db.upsert_document(doc_info)
            except Exception as e:
                log.warning(f"SQLite 入库失败 {case_id}: {e}")
                continue

            # Embedding + Qdrant
            try:
                texts = [c["text"] for c in chunks]
                t0 = time.time()
                embeddings = embedding_service.embed(texts)
                emb_t = time.time() - t0

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
                            "source_type": "case",
                            "source": c["metadata"]["source"],
                            "text": c["text"],
                        }
                    })

                vector_store.upsert_batch(points, collection=CASES_COLLECTION)
                total_chunks += len(chunks)
                log.info(f"  ✓ {case.get('case_no', case_id)} ({len(chunks)} chunks, {emb_t:.1f}s)")

            except Exception as e:
                log.exception(f"案件入库失败 {case_id}: {e}")

        # 批次间隔：让系统 GC
        if batch_num < total_batches:
            log.info(f"  等待 30s 让系统 GC...")
            await asyncio.sleep(30)

    log.info(f"\n=== 完成: {len(cases)} 案件 / {total_chunks} chunks ===")


if __name__ == "__main__":
    asyncio.run(seed_batched())
