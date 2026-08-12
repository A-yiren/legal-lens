"""端到端验收 - 只跑 AI 分析实操，UTF-8 编码"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"PAGE_ERR: {e}"))
        page.on("console", lambda m: m.type == "error" and errors.append(f"CONSOLE: {m.text}"))

        print("loading...")
        await page.goto("https://ayiren.cn/legallens/pages/case-analysis.html", wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1000)
        await page.click("#try-example", timeout=5000)
        case_text = await page.input_value("#case-input")
        print(f"case: {case_text[:60]}...")

        # 改成 top_k=5 减少 LLM token
        await page.select_option("#top-k", "5")

        print("clicking analyze...")
        await page.click("#analyze-btn", timeout=5000)

        # 等待 result-state
        print("waiting for result...")
        try:
            await page.wait_for_selector("#result-state:not(.hidden)", timeout=240000)
            print("OK result visible")
        except Exception as e:
            print(f"FAIL wait: {e}")

        await page.wait_for_timeout(2000)
        await page.screenshot(path="C:\\Users\\34464\\.mavis\\agents\\mavis\\workspace\\legal-lens\\e2e_analysis_done.png", full_page=False)
        print("screenshot saved")

        # 拿文字内容
        if errors:
            print(f"ERRORS: {errors[:5]}")
        else:
            print("NO errors")

        # 拿 result 文字
        result_text = await page.locator("#result-state").text_content()
        print(f"\n--- result first 800 chars ---\n{result_text[:800]}")

        # 拿引用数
        cite_text = await page.locator("#cite-count").text_content()
        print(f"\ncite count: {cite_text}")

        await browser.close()


asyncio.run(main())
