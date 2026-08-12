"""Playwright 端到端验证 v4 - Phase 2 官方源版
- 知识库列表：官方源 badge + 版本 badge + 链接按钮
- 预览弹窗：源 URL 链接 + 版本 + 主席令
- 案例分析：引用真实 + disclaimer
"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v4.log")
def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

OUT_DIR = Path(__file__).parent / "verify-screenshots"
OUT_DIR.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1. 知识库列表 - 验证官方源 badge
        log("[1] 访问知识库页")
        await page.goto("https://ayiren.cn/legallens/pages/knowledge-base.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)

        laws_stat = await page.locator("#stat-laws").text_content()
        chunks_stat = await page.locator("#stat-chunks").text_content()
        vectors_stat = await page.locator("#stat-vectors").text_content()
        log(f"  统计: 法律 {laws_stat} | chunks {chunks_stat} | 向量 {vectors_stat}")

        # 等文档列表加载 - 等待 doc-list 里的 button 出现（预览按钮带 fa-eye）
        await page.wait_for_selector("#doc-list button[onclick^='previewDoc']", timeout=15000)
        await page.wait_for_timeout(1500)

        await page.screenshot(path=str(OUT_DIR / "v4_kb_list.png"), full_page=False)
        log("  [截图] v4_kb_list.png")

        # 滚到中间看更多
        await page.evaluate("document.querySelector('#doc-list')?.scrollIntoView({block:'center'})")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v4_kb_list_scrolled.png"), full_page=False)
        log("  [截图] v4_kb_list_scrolled.png")

        # 2. 点开第一篇预览
        log("[2] 打开第一篇预览")
        # 找第一个 previewDoc 按钮
        first_preview = page.locator("#doc-list button[onclick^='previewDoc']").first
        await first_preview.click(timeout=10000)
        await page.wait_for_timeout(2500)

        # 等 modal 显示
        await page.wait_for_selector("#preview-modal:not(.hidden)", timeout=10000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v4_kb_preview_modal.png"), full_page=False)
        log("  [截图] v4_kb_preview_modal.png")

        # 关闭 modal
        close = page.locator(".modal .btn-close, .modal [data-dismiss='modal']").first
        try:
            await close.click(timeout=3000)
        except Exception:
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(1000)

        # 3. 案例分析
        log("[3] 访问案例分析页")
        await page.goto("https://ayiren.cn/legallens/pages/case-analysis.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)

        await page.screenshot(path=str(OUT_DIR / "v4_case_analysis_empty.png"), full_page=False)
        log("  [截图] v4_case_analysis_empty.png")

        # 4. 首页
        log("[4] 访问首页")
        await page.goto("https://ayiren.cn/legallens/", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v4_home.png"), full_page=False)
        log("  [截图] v4_home.png")

        await browser.close()
        log("DONE")


asyncio.run(main())
