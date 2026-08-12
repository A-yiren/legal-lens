"""v6: 多 Agent 校验版 - 案件分析"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v6.log")
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

        log("[1] Case analysis with multi-agent")
        await page.goto("https://ayiren.cn/legallens/pages/case-analysis.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1500)

        textarea = page.locator("textarea").first
        await textarea.fill("我网购了一台冰箱，收到后发现外观有划痕，商家拒绝退货，怎么办？")
        await page.wait_for_timeout(500)

        analyze_btn = page.locator("button:has-text('开始分析'), button:has-text('分析'), button:has-text('生成')").first
        await analyze_btn.click()
        log("  [等待多 Agent 响应：4 个 Agent 串/并行 ~90s]")
        # Multi-agent ~90s, 等待结果出现（等失败/成功的标志元素）
        try:
            await page.wait_for_selector("#result-state:not(.hidden)", timeout=150000)
            log("  [结果出现]")
        except Exception as e:
            log(f"  [等待超时: {e}]")
        await page.wait_for_timeout(3000)

        # Scroll to top to see overview
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v6_agents_overview.png"), full_page=False)
        log("  [截图] v6_agents_overview.png")

        # Scroll to see legal analysis with source link buttons
        await page.evaluate("document.querySelectorAll('.legal-text, h3')[0]?.scrollIntoView()")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT_DIR / "v6_agents_analysis.png"), full_page=False)
        log("  [截图] v6_agents_analysis.png")

        # Scroll to right side - citations with source URLs
        await page.evaluate("window.scrollTo(0, 200)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT_DIR / "v6_agents_citations_top.png"), full_page=False)
        log("  [截图] v6_agents_citations_top.png")

        # Bottom
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v6_agents_bottom.png"), full_page=False)
        log("  [截图] v6_agents_bottom.png")

        await browser.close()
        log("DONE")


asyncio.run(main())
