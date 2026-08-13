"""本地全量 ingestion v2 - 跑 41 部法规 + 60 判例
- payload 加 category 字段 (law / case) 知识库分类
- 本地 32G 内存可用大 BATCH
- 阶段 1: 41 部法规 → legal_knowledge (category=law)
- 阶段 2: 60 判例 → legal_cases (category=case)
"""
import asyncio
import gc
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.models import DocumentInfo, DocumentStatus, SourceType
from app.services.ingestion import ingestion_service
from app.services.embedding import embedding_service
from app.storage.qdrant_client import vector_store
from app.storage.sqlite import db
from app.utils.logging import log

SEED_LAWS = Path(__file__).parent.parent.parent / "seed_data"
SEED_CASES = Path(__file__).parent.parent.parent / "seed_data_cases"
KNOWLEDGE_COLLECTION = "legal_knowledge"
CASES_COLLECTION = "legal_cases"


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
                "category": "case",  # 知识库分类: 案例
            }
        })
    return chunks


def memory_mb():
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0


async def ingest_one_law(fp):
    """跑单部法规 - 用 ingestion_service.ingest_file 然后给 points 加 category=law"""
    if not fp.exists():
        log.error(f"✗ {fp.name} 不存在")
        return 0
    log.info(f"\n{'='*60}\n入库法规: {fp.name}\n{'='*60}")
    try:
        t0 = time.time()
        doc = await ingestion_service.ingest_file(fp, source=SourceType.SEED)
        elapsed = time.time() - t0
        # 给刚入库的法规点加 category=law
        # 用 doc_id 找到所有 points 然后 set payload
        try:
            await asyncio.to_thread(
                _set_category_for_doc,
                doc.id,
                KNOWLEDGE_COLLECTION,
                "law"
            )
        except Exception as e:
            log.warning(f"  set category 失败: {e}")
        log.info(f"✓ {fp.name}: {doc.chunks_count} chunks, {elapsed:.1f}s, status={doc.status.value}")
        return doc.chunks_count or 0
    except Exception as e:
        log.exception(f"✗ {fp.name} 失败: {e}")
        return 0
    finally:
        gc.collect()


def _set_category_for_doc(doc_id, collection, category):
    """给某 doc 的所有 points payload 加 category"""
    client = vector_store.client
    # 找出 doc_id 的所有点
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    flt = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
    # 用 set_payload 给匹配点加 category
    client.set_payload(
        collection_name=collection,
        payload={"category": category},
        points=flt,
    )


async def ingest_all_laws():
    """阶段 1: 跑所有 .md 法规文件"""
    log.info("\n========== 阶段 1/2: 法规入库 ==========")
    files = sorted(SEED_LAWS.glob("*.md"))
    log.info(f"找到 {len(files)} 部法规")
    total = 0
    for i, fp in enumerate(files, 1):
        n = await ingest_one_law(fp)
        total += n
        if i % 10 == 0:
            log.info(f"进度: {i}/{len(files)} | 总chunks: {total}")
    log.info(f"\n法规完成: {total} chunks (category=law)")
    return total


async def ingest_all_cases():
    """阶段 2: 跑所有 jsonl 判例"""
    log.info("\n========== 阶段 2/2: 判例入库 ==========")
    cases = []
    for fp in SEED_CASES.glob("*.jsonl"):
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

    try:
        vector_store.init_collection(collection=CASES_COLLECTION)
    except Exception as e:
        log.warning(f"Collection 初始化: {e}")

    total_chunks = 0
    total = len(cases)
    for i, case in enumerate(cases, 1):
        case_id = case["id"]
        chunks = chunk_case(case)
        if not chunks:
            continue

        log.info(f"\n[{i}/{total}] {case_id} {case.get('case_no','')} {case.get('title','')[:30]}")

        # SQLite
        try:
            industry = "finance" if "case-1" in case_id and int(case_id.split("-")[1]) >= 100 else "general"
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
                    "source": case.get("source", "seed"),
                    "industry": industry,
                    "category": "case",  # 知识库分类
                }
            )
            db.upsert_document(doc_info)
        except Exception as e:
            log.warning(f"SQLite {case_id}: {e}")
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
                        "tags": c["metadata"]["tags"],
                        "chunk_type": c["chunk_type"],
                        "chunk_index": c["chunk_index"],
                        "source_type": "case",
                        "source": c["metadata"]["source"],
                        "industry": "finance" if "case-1" in case_id and int(case_id.split("-")[1]) >= 100 else "general",
                        "category": "case",  # 知识库分类
                        "text": c["text"],
                    }
                })

            vector_store.upsert_batch(points, collection=CASES_COLLECTION)
            total_chunks += len(chunks)
            log.info(f"  ✓ {len(chunks)} chunks, {emb_t:.1f}s")
        except Exception as e:
            log.exception(f"  ✗ {case_id} 失败: {e}")

        if i % 10 == 0:
            log.info(f"  >> 进度 {i}/{total} | 总chunks: {total_chunks} | mem: {memory_mb():.0f}MB")
            gc.collect()

    log.info(f"\n判例完成: {total} 案件 / {total_chunks} chunks (category=case)")
    return total_chunks


async def main():
    log.info("=== 金睛 RiskLens 本地全量入库 (41 法规 + 60 判例) ===\n")
    t0 = time.time()
    law_chunks = await ingest_all_laws()
    case_chunks = await ingest_all_cases()
    elapsed = time.time() - t0

    log.info(f"\n{'='*60}")
    log.info(f"=== 全部完成 ===")
    log.info(f"  法规 (category=law):  {law_chunks} chunks")
    log.info(f"  案例 (category=case): {case_chunks} chunks")
    log.info(f"  总计: {law_chunks + case_chunks} chunks")
    log.info(f"  用时: {elapsed:.1f}s")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
