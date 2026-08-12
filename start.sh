#!/bin/bash
# 律瞳 LegalLens 一键启动脚本
# 用法：./start.sh [seed]   # seed 参数会自动入库种子数据

set -e

cd "$(dirname "$0")"

echo "=== 律瞳 LegalLens 启动 ==="
echo ""

# 检查 .env
if [ ! -f .env ]; then
    echo "⚠️  .env 不存在，从 .env.example 复制"
    cp .env.example .env
    echo "请编辑 .env 填入 MiniMax_API_KEY 后再启动"
    echo ""
fi

# 创建必要目录
mkdir -p storage/uploads storage/sqlite storage/qdrant storage/logs obsidian_vault

# 启动 Qdrant
echo "▶ 启动 Qdrant 向量库..."
docker compose up -d qdrant

# 等待 Qdrant 就绪
echo "▶ 等待 Qdrant 就绪..."
for i in {1..30}; do
    if curl -s http://localhost:6333/health > /dev/null 2>&1; then
        echo "  ✓ Qdrant 已就绪"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "  ✗ Qdrant 启动超时"
        exit 1
    fi
    sleep 2
done

# 启动 Backend
echo "▶ 启动 Backend..."
docker compose up -d backend

echo ""
echo "✓ 启动完成！"
echo ""
echo "  - API 文档: http://localhost:8765/docs"
echo "  - Qdrant Dashboard: http://localhost:6333/dashboard"
echo ""

# 可选：种子数据入库
if [ "$1" == "seed" ]; then
    echo "▶ 入库种子数据..."
    sleep 5  # 等待 backend 初始化
    docker compose exec backend python /app/../scripts/seed_data.py 2>/dev/null || \
    docker compose exec backend python -c "
import sys
sys.path.insert(0, '/app')
from app.models import SourceType
from app.services.ingestion import ingestion_service
import asyncio
from pathlib import Path

async def run():
    for f in Path('/seed_data').rglob('*.md'):
        print(f'入库: {f.name}')
        try:
            await ingestion_service.ingest_file(f, source=SourceType.SEED)
        except Exception as e:
            print(f'  失败: {e}')

asyncio.run(run())
" || echo "⚠️  种子数据入库失败（可手动执行 python scripts/seed_data.py）"
fi

echo ""
echo "查看日志: docker compose logs -f backend"
