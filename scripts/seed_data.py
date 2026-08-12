"""种子数据入库脚本 - 把 seed_data 目录下的法律文件全部入库"""
import asyncio
import sys
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models import SourceType
from app.services.ingestion import ingestion_service
from app.utils.logging import log


SEED_DIR = Path(__file__).parent.parent / "seed_data"


async def main():
    log.info(f"开始种子数据入库: {SEED_DIR}")

    if not SEED_DIR.exists():
        log.error(f"种子数据目录不存在: {SEED_DIR}")
        return

    files = list(SEED_DIR.rglob("*.md")) + list(SEED_DIR.rglob("*.pdf")) + list(SEED_DIR.rglob("*.docx"))
    log.info(f"找到 {len(files)} 个文件")

    for f in files:
        try:
            log.info(f"入库: {f.relative_to(SEED_DIR)}")
            doc = await ingestion_service.ingest_file(
                f,
                source=SourceType.SEED,
            )
            log.info(f"  ✓ {doc.chunks_count} chunks, status={doc.status.value}")
        except Exception as e:
            log.exception(f"  ✗ 失败: {e}")

    log.info("种子数据入库完成")


if __name__ == "__main__":
    asyncio.run(main())
