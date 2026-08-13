"""v10: 截案件库页面（修复后）"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v10.log")
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
        await page.goto("https://ayiren.cn/legallens/pages/case-list.html",
                        wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        out = OUT_DIR / "v10_case_list.png"
        await page.screenshot(path=str(out), full_page=False)
        log(f"[截图] {out.name}")
        await browser.close()
        log("DONE")


asyncio.run(main())
