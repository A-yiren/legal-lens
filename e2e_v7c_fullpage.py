"""v7c: full_page 截图合同审查完整长图"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v7c.log")
def log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

OUT_DIR = Path(__file__).parent / "verify-screenshots"
OUT_DIR.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await ctx.new_page()

        await page.goto("https://ayiren.cn/legallens/pages/contract-review.html",
                        wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.locator(".example-btn[data-type='labor']").click()
        await page.wait_for_timeout(1000)
        await page.locator("#review-btn").click()
        log("[等待审查响应...]")
        try:
            await page.wait_for_selector("#results-container h2", timeout=120000)
            log("[审查完成]")
        except Exception as e:
            log(f"[超时: {e}]")
        await page.wait_for_timeout(2000)

        # 完整长图
        out = OUT_DIR / "v7c_contract_full.png"
        await page.screenshot(path=str(out), full_page=True)
        log(f"[截图] {out.name}")

        # 完整页面内容
        body_height = await page.evaluate("document.documentElement.scrollHeight")
        log(f"页面总高度: {body_height}px")

        await browser.close()
        log("DONE")


asyncio.run(main())
