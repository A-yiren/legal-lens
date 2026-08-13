"""v9: 截 case-030 环境污染侵权案的预览 modal"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v9.log")
def log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

OUT = Path(__file__).parent / "verify-screenshots" / "v9_case_modal.png"
OUT.parent.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await ctx.new_page()

        # 直接用 URL 打开带 ?preview=case-030
        await page.goto(
            "https://ayiren.cn/legallens/pages/knowledge-base.html?preview=case-030",
            wait_until="networkidle",
            timeout=60000,
        )
        # 等 modal 出现
        log("等 modal 出现...")
        try:
            await page.wait_for_selector("#preview-modal:not(.hidden)", timeout=30000)
            log("modal 出现")
        except Exception as e:
            log(f"modal 未出现: {e}")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT), full_page=False)
        log(f"[截图] {OUT.name}")
        await browser.close()
        log("DONE")


asyncio.run(main())
