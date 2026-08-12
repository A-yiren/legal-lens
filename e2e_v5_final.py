"""v5 final: KB list + preview + analyze result (full RAG)"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v5.log")
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
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1100})
        page = await ctx.new_page()

        # 1. KB list
        log("[1] KB list")
        await page.goto("https://ayiren.cn/legallens/pages/knowledge-base.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.wait_for_selector("#doc-list button[onclick^='previewDoc']", timeout=15000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v5_kb_list.png"), full_page=False)

        # 2. Preview modal
        log("[2] Preview modal")
        first_preview = page.locator("#doc-list button[onclick^='previewDoc']").first
        await first_preview.click(timeout=10000)
        await page.wait_for_timeout(2500)
        await page.wait_for_selector("#preview-modal:not(.hidden)", timeout=10000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v5_kb_preview.png"), full_page=False)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(800)

        # 3. Analyze with real case
        log("[3] Case analysis - real LLM RAG")
        await page.goto("https://ayiren.cn/legallens/pages/case-analysis.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)

        # Type the case
        textarea = page.locator("textarea").first
        await textarea.fill("我网购了一台冰箱，收到后发现外观有划痕，商家拒绝退货，怎么办？")
        await page.wait_for_timeout(500)

        # Click analyze button
        analyze_btn = page.locator("button:has-text('开始分析'), button:has-text('分析'), button:has-text('生成')").first
        await analyze_btn.click()
        log("  [等待 LLM 响应...]")
        # LLM cold start: 60-120s
        await page.wait_for_timeout(90000)
        # Scroll to result
        await page.evaluate("window.scrollTo(0, 600)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v5_case_analysis_result.png"), full_page=False)
        log("  [截图] v5_case_analysis_result.png")

        # Scroll further to see citations
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v5_case_analysis_citations.png"), full_page=False)
        log("  [截图] v5_case_analysis_citations.png")

        await browser.close()
        log("DONE")


asyncio.run(main())
