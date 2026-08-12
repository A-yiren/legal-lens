"""验收知识库搜索功能"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGE_ERR: {e}"))
        page.on("console", lambda m: m.type == "error" and errors.append(f"CONSOLE: {m.text}"))

        await page.goto("https://ayiren.cn/legallens/pages/knowledge-base.html", wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        # 输入搜索词
        await page.fill("#search-input", "合同解除")
        await page.click("#do-search")
        print("searching...")
        await page.wait_for_timeout(5000)
        # 拿结果
        result = await page.locator("#search-results").text_content()
        print(f"\n--- search result ---\n{result[:600]}")
        if errors:
            print(f"\nERRORS: {errors[:5]}")
        else:
            print("\nNO errors")
        await page.screenshot(path="C:\\Users\\34464\\.mavis\\agents\\mavis\\workspace\\legal-lens\\e2e_search.png", full_page=False)
        print("screenshot saved")
        await browser.close()


asyncio.run(main())
