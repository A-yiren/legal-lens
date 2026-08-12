"""v7d: 用 main 内部滚动器滚合同审查结果"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v7d.log")
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
        await page.wait_for_selector("#results-container h2", timeout=120000)
        log("[审查完成]")
        await page.wait_for_timeout(2000)

        scroll_js = """() => {
            const sc = document.querySelector('div.flex-1.overflow-y-auto');
            if (sc) { sc.scrollTop = 0; return sc.scrollHeight; }
            return 0;
        }"""
        height = await page.evaluate(scroll_js)
        log(f"main 内部滚动容器总高度: {height}px")

        # 第 1 张: 顶部
        await page.evaluate("() => document.querySelector('div.flex-1.overflow-y-auto').scrollTop = 0")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v7d_top.png"), full_page=False)
        log("[1] top")

        # 第 2 张: 中部
        await page.evaluate("() => document.querySelector('div.flex-1.overflow-y-auto').scrollTop = 600")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v7d_mid.png"), full_page=False)
        log("[2] mid")

        # 第 3 张: 底部
        max_top = max(0, height - 1000)
        await page.evaluate(f"() => document.querySelector('div.flex-1.overflow-y-auto').scrollTop = {max_top}")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v7d_bot.png"), full_page=False)
        log(f"[3] bottom (top={max_top})")

        await browser.close()
        log("DONE")


asyncio.run(main())
