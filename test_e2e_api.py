"""通过 API 端到端测试 RAG"""
import sys
import json
import httpx
import time

API = "http://127.0.0.1:8767"

case = """2023 年 3 月原告张某与被告某科技公司签订软件开发合同，约定 6 个月开发周期，总价款 128 万元。原告支付首期款 51.2 万元后，被告多次延期。2024 年 1 月，被告单方通知解除合同。原告认为被告构成根本违约，要求返还已付款并赔偿损失。"""

print(f"案情: {case[:60]}...")
print(f"案情长度: {len(case)} 字符\n")

print("=" * 60)
print("[1/3] 检索相关法条")
print("=" * 60)
with httpx.Client(timeout=120) as client:
    r = client.post(
        f"{API}/api/knowledge/search",
        params={"query": case, "top_k": 5},
    )
    data = r.json()
    print(f"召回 {data['count']} 条:")
    for i, hit in enumerate(data["results"], 1):
        print(f"  [{i}] {hit['law_name']} {hit['article_no']} - score: {hit['score']:.3f}")

    print("\n" + "=" * 60)
    print("[2/3] RAG 分析（需要 LLM）")
    print("=" * 60)
    t0 = time.time()
    r = client.post(
        f"{API}/api/analyze",
        json={"case_description": case, "top_k": 5},
        timeout=120,
    )
    elapsed = time.time() - t0
    print(f"耗时: {elapsed:.1f}s")
    result = r.json()
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
    print("[3/3] 引用溯源验证")
    print("=" * 60)
    for c in result.get("citations", [])[:3]:
        print(f"  [{c['id']}] {c['law_name']} {c['article_no']} (相关度 {c['similarity']:.3f})")
        print(f"      {c['article_text'][:100]}...")

print("\n" + "=" * 60)
print("✓ 端到端测试完成")
