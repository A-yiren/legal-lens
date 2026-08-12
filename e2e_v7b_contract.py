"""v7b: 重跑合同审查 4 张截图（修了 contractType bug）"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v7b.log")
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
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
        page = await ctx.new_page()

        # 合同审查
        log("[1] 合同审查 - 加载示例")
        await page.goto("https://ayiren.cn/legallens/pages/contract-review.html",
                        wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.locator(".example-btn[data-type='labor']").click()
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT_DIR / "v7b_contract_filled.png"), full_page=False)
        log("  [截图] v7b_contract_filled.png")

        log("[2] 合同审查 - 提交审查")
        await page.locator("#review-btn").click()
        log("  [等待合同审查响应...]")
        try:
            await page.wait_for_selector("#results-container h2", timeout=120000)
            log("  [审查结果已显示]")
        except Exception as e:
            log(f"  [等待超时: {e}]")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v7b_contract_results_top.png"), full_page=False)
        log("  [截图] v7b_contract_results_top.png")

        log("[3] 风险详情")
        await page.evaluate("window.scrollTo(0, 600)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v7b_contract_results_risks.png"), full_page=False)
        log("  [截图] v7b_contract_results_risks.png")

        log("[4] 缺失条款")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v7b_contract_results_missing.png"), full_page=False)
        log("  [截图] v7b_contract_results_missing.png")

        await browser.close()
        log("DONE")


asyncio.run(main())
