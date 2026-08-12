"""端到端测试: 真实案情 → 检索 → LLM 生成 → 引用"""
import sys
sys.path.insert(0, '/opt/legal-lens/backend')
import asyncio
import json

from app.services.generation import generation_service
from app.services.retrieval import retrieval_service


async def main():
    case = """2023 年 3 月原告张某与被告某科技公司签订软件开发合同，约定 6 个月开发周期，总价款 128 万元。原告支付首期款 51.2 万元后，被告多次延期。2024 年 1 月，被告单方通知解除合同。原告认为被告构成根本违约，要求返还已付款并赔偿损失。"""
    print(f"案情: {case[:60]}...")
    print(f"案情长度: {len(case)} 字符\n")

    print("=" * 60)
    print("[1/3] 检索相关法条...")
    print("=" * 60)
    results = await retrieval_service.search(case, top_k=8, use_rerank=False)
    print(f"召回 {len(results)} 条:")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r.law_name} {r.article_no} - score: {r.score:.3f}")

    if not results:
        print("✗ 没召回任何法条！")
        return

    print("\n" + "=" * 60)
    print("[2/3] RAG 生成分析...")
    print("=" * 60)
    result = await generation_service.analyze(case, top_k=8)

    print(f"分析 ID: {result.get('analysis_id')}")
    print(f"置信度: {result.get('confidence')}")
    print(f"引用数: {len(result.get('citations', []))}")

    print("\n--- 案件焦点 ---")
    for f in result.get("case_focus", []):
        print(f"  • {f}")

    print("\n--- 法律分析 ---")
    for item in result.get("legal_analysis", []):
        text = item.get("point", "")
        cites = item.get("citations", [])
        cite_str = ", ".join(f"[{c}]" for c in cites)
        print(f"\n  ▸ {text}")
        if cite_str:
            print(f"    引用: {cite_str}")

    print("\n--- 风险 ---")
    for r in result.get("risks", []):
        print(f"  ⚠ {r}")

    print("\n--- 下一步建议 ---")
    for i, s in enumerate(result.get("next_steps", []), 1):
        print(f"  {i}. {s}")

    print("\n" + "=" * 60)
    print("[3/3] 验证引用溯源...")
    print("=" * 60)
    for c in result.get("citations", [])[:3]:
        print(f"  [{c['id']}] {c['law_name']} {c['article_no']} (相关度 {c['similarity']:.3f})")
        print(f"      {c['article_text'][:80]}...")


asyncio.run(main())
