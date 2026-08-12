"""v7: 类案检索 + 合同审查 完整截图"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG = Path(r"C:\Users\34464\AppData\Local\Temp\e2e_v7.log")
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

        # 1. 类案检索 - 空状态
        log("[1] 类案检索 - 空状态")
        await page.goto("https://ayiren.cn/legallens/pages/case-search.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "v7_case_search_empty.png"), full_page=False)
        log("  [截图] v7_case_search_empty.png")

        # 2. 类案检索 - 输入并搜索
        log("[2] 类案检索 - 搜索结果")
        await page.locator("#query-input").fill("网购冰箱有划痕，商家拒绝退货")
        await page.locator("#search-btn").click()
        log("  [等待类案检索响应...]")
        # 等待结果出现
        try:
            await page.wait_for_selector("#results-container .case-card", timeout=90000)
            log("  [类案结果已显示]")
        except Exception as e:
            log(f"  [等待超时: {e}]")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "v7_case_search_results.png"), full_page=False)
        log("  [截图] v7_case_search_results.png")

        # 3. 展开一个案件详情
        log("[3] 展开案件详情")
        first_card = page.locator(".case-card").first
        await first_card.click()
        await page.wait_for_timeout(2000)
        await page.evaluate("document.querySelectorAll('.case-card')[0].scrollIntoView({block:'start'})")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v7_case_search_detail.png"), full_page=False)
        log("  [截图] v7_case_search_detail.png")

        # 4. 合同审查 - 空状态
        log("[4] 合同审查 - 空状态")
        await page.goto("https://ayiren.cn/legallens/pages/contract-review.html", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT_DIR / "v7_contract_empty.png"), full_page=False)
        log("  [截图] v7_contract_empty.png")

        # 5. 合同审查 - 用劳动合同示例
        log("[5] 合同审查 - 加载示例")
        await page.locator(".example-btn[data-type='labor']").click()
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT_DIR / "v7_contract_filled.png"), full_page=False)
        log("  [截图] v7_contract_filled.png")

        # 6. 合同审查 - 跑审查
        log("[6] 合同审查 - 提交审查")
        await page.locator("#review-btn").click()
        log("  [等待合同审查响应...]")
        try:
            await page.wait_for_selector("#results-container h3", timeout=120000)
            log("  [审查结果已显示]")
        except Exception as e:
            log(f"  [等待超时: {e}]")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT_DIR / "v7_contract_results_top.png"), full_page=False)
        log("  [截图] v7_contract_results_top.png")

        # 7. 滚到中间看风险详情
        log("[7] 合同审查 - 风险详情")
        await page.evaluate("window.scrollTo(0, 600)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v7_contract_results_risks.png"), full_page=False)
        log("  [截图] v7_contract_results_risks.png")

        # 8. 滚到底看缺失条款
        log("[8] 合同审查 - 缺失条款")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT_DIR / "v7_contract_results_missing.png"), full_page=False)
        log("  [截图] v7_contract_results_missing.png")

        await browser.close()
        log("DONE")


asyncio.run(main())
